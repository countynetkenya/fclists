"""FCLists live VERIFIER (D-042 parity sweep — modelled on fcduka/fcduka/api/_verify_fclists.py).

Proves, on a real site (group.localhost), that the FCLists surface is wired correctly and stays
sector-neutral + config-not-fork + upgrade-safe. Four families of checks:

  (1) LIST-JS WIRING (Finding A) — every doctype_list_js entry in fclists/hooks.py resolves to a real
      file on disk that EXTENDS the native listview via `fclists.extend_listview(` and NOT via a bare
      `frappe.listview_settings["X"] = {` reassignment (Frappe concatenates every app's list-js; a bare
      assignment clobbers ERPNext's native config for the doctype).
  (2) LOADER PRIMITIVE — public/js/fclists_lib.js exists and DEFINES `fclists.extend_listview` (the merge
      -and-chain helper that (1) depends on).
  (3) REPORT SECURITY + EXECUTION (Finding B) — every Wave-1 AND Wave-2 report exists as a Script Report
      with a ref_doctype, is ROLE-GATED (non-empty roles — never world-readable), and actually EXECUTES +
      renders through frappe's own runner `frappe.desk.query_report.run` (the same path CSV/print export use).
  (3b) BI FIXTURES — every fclists BI fixture (Dashboard / Dashboard Chart / Number Card) is present, parses,
      ships only FClist-prefixed rows, and references NO Frappe Insights / foreign BI app (BI is built on
      NATIVE frappe core doctypes only; Insights may be LINKED at runtime but is NEVER required).
  (4) DEPENDENCY HYGIENE — required_apps == ["erpnext"] EXACTLY, and NO fclists source file imports
      flowcore / fcduka / titan_mpsa / titan / settle / leanorg (grep the whole tree).
  (5) SECURITY DENY + ALLOW-AS-PERSONA (sw/testing.md §2 — a permission verifier without the denial
      is a half-test, and an ALLOW proven only as Administrator is the other half-test):
      a seeded ROLE-LESS user is REFUSED by the real runner (frappe.desk.query_report.run raises
      PermissionError on a gated Accounts report AND a gated Stock report); the guide gate
      (www/fclists-guide.get_context) refuses Guest + the role-less user while rendering for
      Administrator; AND for EVERY report a throwaway user holding exactly ONE admitted non-admin
      role runs it successfully through the runner (catches role tables that admit only DEAD roles —
      e.g. a ref_doctype whose 'report' permission never reaches the roles the Report doc admits).
  (6) USER-PERMISSION SCOPING — two throwaway Companies (Alpha/Beta) + an Accounts User restricted by a
      User Permission to Alpha: the scoped user's FClist Account run returns Alpha rows and ZERO Beta rows
      (Administrator first proves the Beta rows exist, so the DENY can never pass vacuously); explicitly
      filtering for Beta returns nothing. Self-seeded, torn down in finally.
  (7) SHELL FIXTURES ON SITE — Workspace / Workspace Sidebar / Desktop Icon / Dashboard / Dashboard Chart /
      Number Card docs actually EXIST on the site (frappe.db.exists), not just as JSON files — a failed
      fixture sync (the S033 sidebar-snapshot failure mode) goes RED here.
  (8) REPORT-PERIOD PRESET FILTER (yokoten of fcreports/fcreports/periods.py into FCLists' Query Report
      filter paradigm) — public/js/fclists_periods.js exists and defines the PERIODS registry + resolve()
      + filter_def(); it is declared in hooks.app_include_js (so every desk page has it, matching
      fclists_lib.js's own wiring); fclists/periods.py exists, is whitelisted, and its resolve_fiscal_period
      genuinely EXECUTES for both fiscal keys (returning a from_date/to_date pair even with no Fiscal Year
      configured — the documented calendar-fallback contract) while rejecting an unknown key; and every
      Script Report whose filters carry a from_date/to_date pair ALSO splices `fclists.periods.filter_def()`
      into that same filters array (source-scanned — a report that grew its own date range after this
      preset shipped, without wiring the preset, goes RED here instead of silently drifting).

Self-contained, idempotent; sections 1-4 + 7-8 are read-only, sections 5-6 seed neutral throwaway users/
companies and tear them down (safe on a shared site with real data). Prints a numbered PASS/FAIL per
check, a rolled-up "N/N", and a final "all_ok: true/false".

Run:  bench --site group.localhost execute fclists.scripts._verify_fclists.run
"""

import importlib
import json
import os
import re

import frappe
from frappe.desk.query_report import run as run_report

# Wave-1 reports, referenced by DISPLAY NAME (exactly as declared in each report JSON's report_name).
WAVE1_REPORTS = [
	"FClist Item Stock",
	"FClist Reorder",
	"FClist Batch Expiry",
	"FClist Stock Movement",
	"FClist Sales Invoice",
	"FClist POS Invoice",
	"FClist Sales History",
	"FClist Returns",
	"FClist Payments",
]

# Wave-2 reports (D-042 parity sweep continuation), referenced by DISPLAY NAME. Same contract as Wave-1:
# each is a role-gated Script Report over NATIVE erpnext doctypes and must EXECUTE through the real runner.
WAVE2_REPORTS = [
	"FClist Best Sellers",
	"FClist Sales by Cashier",
	"FClist Sales by Department",
	"FClist Sales YoY",
	"FClist Customer Balance",
	"FClist Open Invoices",
	"FClist Supplier Balance",
	"FClist Purchase Invoice",
	"FClist Account",
	"FClist GL",
	"FClist Bank Reconciliation Queue",
]

# Wave-3 reports (QB-POS parity borrows, S035 — the agrovet's live Payment Summary + Sales Receipt Detail
# screens). Same contract: role-gated Script Reports over NATIVE erpnext doctypes, executed via the runner.
WAVE3_REPORTS = [
	"FClist Payment Summary",
	"FClist Receipt Detail",
]

# All reports the verifier gates (Wave-1 + Wave-2 + Wave-3). Existence / role-gating / execution apply to
# every one.
REPORTS = WAVE1_REPORTS + WAVE2_REPORTS + WAVE3_REPORTS

# Reports whose filters carry a from_date/to_date pair — each of these MUST also splice
# `fclists.periods.filter_def()` into its filters array (section 8). Keyed by DISPLAY NAME -> the report's
# module-relative .js path (…/apps/fclists/fclists/fclists/report/<folder>/<folder>.js).
DATE_RANGE_REPORT_JS = {
	"FClist Bank Reconciliation Queue": "fclists/report/fclist_bank_reconciliation_queue/fclist_bank_reconciliation_queue.js",
	"FClist Cost Adjustment": "fclists/report/fclist_cost_adjustment/fclist_cost_adjustment.js",
	"FClist GL": "fclists/report/fclist_gl/fclist_gl.js",
	"FClist Payment Summary": "fclists/report/fclist_payment_summary/fclist_payment_summary.js",
	"FClist Payments": "fclists/report/fclist_payments/fclist_payments.js",
	"FClist POS Invoice": "fclists/report/fclist_pos_invoice/fclist_pos_invoice.js",
	"FClist Purchase Invoice": "fclists/report/fclist_purchase_invoice/fclist_purchase_invoice.js",
	"FClist Receipt Detail": "fclists/report/fclist_receipt_detail/fclist_receipt_detail.js",
	"FClist Receiving": "fclists/report/fclist_receiving/fclist_receiving.js",
	"FClist Returns": "fclists/report/fclist_returns/fclist_returns.js",
	"FClist Sales by Cashier": "fclists/report/fclist_sales_by_cashier/fclist_sales_by_cashier.js",
	"FClist Sales by Department": "fclists/report/fclist_sales_by_department/fclist_sales_by_department.js",
	"FClist Sales History": "fclists/report/fclist_sales_history/fclist_sales_history.js",
	"FClist Sales Invoice": "fclists/report/fclist_sales_invoice/fclist_sales_invoice.js",
	"FClist Stock Movement": "fclists/report/fclist_stock_movement/fclist_stock_movement.js",
}

# Wave-2 list-JS doctypes that MUST be declared in fclists.hooks.doctype_list_js (each resolves to a
# *_list.js that EXTENDS native via fclists.extend_listview() — proven by the generic wiring loop below).
WAVE2_LIST_JS_DOCTYPES = ["Customer", "Supplier", "Purchase Invoice", "Account"]

# fclists BI fixtures (NATIVE frappe core doctypes only). Each fixture file must be present, parse as JSON,
# and reference NO Frappe Insights / foreign-BI app. document_type / based_on stay on native erpnext/frappe
# doctypes. Keyed by the fixture file under fclists/fclists/fixtures/.
BI_FIXTURE_FILES = {
	"Dashboard": "dashboard.json",
	"Dashboard Chart": "dashboard_chart.json",
	"Number Card": "number_card.json",
}

# BI must be built on frappe/erpnext core only — any reference to these BI apps (as a document_type, an
# import, or a stringy token in the fixture JSON) fails the "no foreign BI app" gate. Insights may be LINKED
# at runtime but NEVER required, and our shipped fixtures must not hard-reference it.
FORBIDDEN_BI_TOKENS = ["insights", "Insights", "frappe_insights", "posthog", "metabase", "superset"]

# Apps that fclists must NEVER import or depend on (single-owner / config-not-fork law). erpnext is the
# only permitted dependency. Matched as `import X` / `from X` and dotted-attribute use `X.` in source.
FORBIDDEN_APPS = ["flowcore", "fcduka", "titan_mpsa", "titan", "settle", "leanorg"]

# Client literals that must never appear in fclists source (sector-neutral, config-driven — D-002/D-024).
FORBIDDEN_LITERALS = ["Vets", "Agrovet", "Busara", "Diamante"]

# --- security-fixture constants (sections 5+6). NEUTRAL names only; every doc below is seeded by this
# verifier and torn down in its finally block (safe + idempotent on a shared site with real data).
DENY_USER = "fclists-verify-noroles@example.com"     # role-less → every gated report must REFUSE
ALLOW_USER = "fclists-verify-persona@example.com"    # one admitted non-admin role at a time → must RUN
SCOPED_USER = "fclists-verify-scoped@example.com"    # Accounts User, User-Permission-locked to Alpha
COMPANY_ALPHA = "FCList Verify Co Alpha"             # abbr FCLVA — the scoped user's permitted company
COMPANY_BETA = "FCList Verify Co Beta"               # abbr FCLVB — must stay INVISIBLE to the scoped user
ABBR_ALPHA = "FCLVA"
ABBR_BETA = "FCLVB"


def _app_path():
	"""Absolute path to the fclists app module dir (…/apps/fclists/fclists)."""
	return frappe.get_app_path("fclists")


def _read(path):
	try:
		with open(path, "r", encoding="utf-8") as fh:
			return fh.read()
	except OSError:
		return None


def _strip_js_comments(src):
	"""Drop full-line `//`, `/* */` and JSDoc `*` comment lines so the anti-pattern check scans CODE
	only. Our list_js files reference the bare `frappe.listview_settings["X"] = {` string inside warning
	comments; without this, that comment triggers a false-red on an otherwise-compliant file."""
	out, in_block = [], False
	for line in (src or "").splitlines():
		s = line.strip()
		if in_block:
			if "*/" in s:
				in_block = False
			continue
		if s.startswith("/*"):
			in_block = "*/" not in s
			continue
		if s.startswith("//") or s.startswith("*"):
			continue
		out.append(line)
	return "\n".join(out)


def _ensure_user(email, first_name, roles):
	"""Create-or-reset a throwaway verifier user with EXACTLY the given roles (idempotent)."""
	if not frappe.db.exists("User", email):
		user = frappe.new_doc("User")
		user.update({"email": email, "first_name": first_name, "send_welcome_email": 0, "enabled": 1})
		user.flags.no_welcome_mail = True
		user.insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	for role in roles:
		user.append("roles", {"role": role})
	user.flags.ignore_permissions = True
	user.save(ignore_permissions=True)
	frappe.clear_cache(user=email)
	return email


def _ensure_company(name, abbr):
	"""Create a throwaway Company (idempotent). Currency/country borrowed from the site's first company
	so the verifier stays neutral on any bench (NO invented geography defaults — a site with no Company
	fails RED with a clear message instead); on_trash cleanly deletes its CoA (no transactions)."""
	if frappe.db.exists("Company", name):
		return name
	first = frappe.get_all(
		"Company", fields=["default_currency", "country"], order_by="creation asc", limit=1
	)
	if not first or not (first[0].default_currency and first[0].country):
		frappe.throw(
			"site has no Company to borrow currency/country defaults from — seed one real "
			"Company before running the fclists verifier (the fixture invents NO defaults)"
		)
	frappe.get_doc({
		"doctype": "Company",
		"company_name": name,
		"abbr": abbr,
		"default_currency": first[0].default_currency,
		"country": first[0].country,
	}).insert(ignore_permissions=True)
	return name


def _teardown_security_fixture():
	"""Delete everything sections 5+6 seeded — leave the site as found. Each delete is individually
	guarded so a partial failure never blocks the rest of the teardown."""
	frappe.set_user("Administrator")
	for up in frappe.get_all(
		"User Permission", filters={"user": SCOPED_USER}, pluck="name", order_by="name asc"
	):
		try:
			frappe.delete_doc("User Permission", up, force=True, ignore_permissions=True)
		except Exception:
			pass
	for email in (DENY_USER, ALLOW_USER, SCOPED_USER):
		# frappe auto-creates a Contact per new User — remove it too or re-runs accumulate orphans.
		for contact in frappe.get_all("Contact", filters={"user": email}, pluck="name", order_by="name asc"):
			try:
				frappe.delete_doc("Contact", contact, force=True, ignore_permissions=True)
			except Exception:
				pass
		if frappe.db.exists("User", email):
			try:
				frappe.delete_doc("User", email, force=True, ignore_permissions=True)
			except Exception:
				pass
	for comp in (COMPANY_BETA, COMPANY_ALPHA):
		if not frappe.db.exists("Company", comp):
			continue
		# Company insert auto-creates departments + country tax templates; on_trash does not remove
		# them — clear those first (departments leaf-first: NestedSet).
		for dep in frappe.get_all(
			"Department", filters={"company": comp}, pluck="name", order_by="lft desc"
		):
			try:
				frappe.delete_doc("Department", dep, force=True, ignore_permissions=True)
			except Exception:
				pass
		for tax_dt in (
			"Sales Taxes and Charges Template", "Purchase Taxes and Charges Template", "Item Tax Template"
		):
			for tpl in frappe.get_all(tax_dt, filters={"company": comp}, pluck="name", order_by="name asc"):
				try:
					frappe.delete_doc(tax_dt, tpl, force=True, ignore_permissions=True)
				except Exception:
					pass
		try:
			frappe.delete_doc("Company", comp, force=True, ignore_permissions=True)
		except Exception:
			pass


def run():
	checks = []

	def record(name, passed, detail=""):
		checks.append({"check": name, "ok": bool(passed), "detail": str(detail)})

	app_path = _app_path()

	# ----------------------------------------------------------------------------------------------
	# (1) LIST-JS WIRING (Finding A) — resolve every doctype_list_js hook to a real extend_listview file.
	# ----------------------------------------------------------------------------------------------
	hooks = frappe.get_hooks(app_name="fclists")
	# doctype_list_js in hooks.py is a dict {doctype: relpath}; frappe.get_hooks flattens dict values into
	# a list, so read the raw module to keep the doctype→path mapping intact.
	list_js_map = {}
	try:
		import fclists.hooks as _fh  # noqa: PLC0415

		raw = getattr(_fh, "doctype_list_js", {}) or {}
		if isinstance(raw, dict):
			list_js_map = dict(raw)
	except Exception as e:  # noqa: BLE001
		record("list_js:hooks_import", False, f"{type(e).__name__}: {e}")

	record("list_js:entries_present", len(list_js_map) > 0, f"{len(list_js_map)} doctype_list_js entries")

	# Wave-2 wiring: each new doctype MUST be declared in doctype_list_js. The generic loop below then proves
	# the declared file EXTENDS native via fclists.extend_listview() and carries no bare reassignment.
	for doctype in WAVE2_LIST_JS_DOCTYPES:
		record(f"list_js:wave2_declared:{doctype}", doctype in list_js_map,
			list_js_map.get(doctype, "MISSING from doctype_list_js"))

	for doctype, relpath in sorted(list_js_map.items()):
		# hook paths are relative to the app module dir (e.g. "public/js/item_list.js").
		fpath = os.path.join(app_path, relpath.replace("/", os.sep))
		src = _read(fpath)
		if src is None:
			record(f"list_js:file:{doctype}", False, f"missing {relpath}")
			continue
		record(f"list_js:file:{doctype}", True, relpath)

		uses_helper = "fclists.extend_listview(" in src
		record(f"list_js:extends:{doctype}", uses_helper, "uses fclists.extend_listview(")

		# A bare `frappe.listview_settings["X"] = {` (or ['X'] = {) reassignment clobbers native config.
		# Scan CODE ONLY — the files name the anti-pattern in warning comments (would false-red otherwise).
		bare = re.search(r"frappe\.listview_settings\s*\[[^\]]+\]\s*=\s*\{", _strip_js_comments(src))
		record(f"list_js:no_bare_assign:{doctype}", bare is None,
			"no bare listview_settings[...] = {" if bare is None else f"BARE assignment: {bare.group(0)}")

	# ----------------------------------------------------------------------------------------------
	# (2) LOADER PRIMITIVE — fclists_lib.js exists and defines fclists.extend_listview.
	# ----------------------------------------------------------------------------------------------
	lib_path = os.path.join(app_path, "public", "js", "fclists_lib.js")
	lib_src = _read(lib_path)
	record("lib:exists", lib_src is not None, "public/js/fclists_lib.js")
	if lib_src is not None:
		defines = ("fclists.extend_listview =" in lib_src) or ("fclists.extend_listview=" in lib_src)
		record("lib:defines_extend_listview", defines, "defines fclists.extend_listview")

	# ----------------------------------------------------------------------------------------------
	# (3) REPORT SECURITY + EXECUTION (Finding B) — Script Report, ref_doctype, role-gated, executes.
	# ----------------------------------------------------------------------------------------------
	for rname in REPORTS:
		exists = frappe.db.exists("Report", rname)
		record(f"report:exists:{rname}", exists, rname)
		if not exists:
			continue

		doc = frappe.get_doc("Report", rname)
		record(f"report:script:{rname}", doc.report_type == "Script Report", doc.report_type)
		record(f"report:ref_doctype:{rname}", bool(doc.ref_doctype), doc.ref_doctype)
		record(f"report:role_gated:{rname}", len(doc.roles) > 0, f"{len(doc.roles)} roles")

		# End-to-end: the report actually runs + returns columns and a list result via the SAME runner
		# CSV/print export use (proves it is not just declared but genuinely renders).
		try:
			res = run_report(rname, filters={})
			cols = res.get("columns") if isinstance(res, dict) else None
			data = res.get("result") if isinstance(res, dict) else None
			record(f"report:executes:{rname}", bool(cols) and isinstance(data, list),
				f"cols={bool(cols)} rows={len(data) if isinstance(data, list) else 'n/a'}")
		except Exception as e:  # noqa: BLE001
			record(f"report:executes:{rname}", False, f"{type(e).__name__}: {e}")

	# ----------------------------------------------------------------------------------------------
	# (3b) BI FIXTURES — each Dashboard / Dashboard Chart / Number Card fixture is present, parses as JSON,
	# ships at least one FClist-prefixed row, and references NO Frappe Insights / foreign BI app (BI is built
	# on NATIVE frappe core doctypes only — Insights may be LINKED at runtime but is NEVER required).
	# ----------------------------------------------------------------------------------------------
	fixtures_dir = os.path.join(app_path, "fixtures")
	for label, fname in BI_FIXTURE_FILES.items():
		fpath = os.path.join(fixtures_dir, fname)
		raw = _read(fpath)
		record(f"bi:fixture_present:{label}", raw is not None, f"fixtures/{fname}")
		if raw is None:
			continue

		try:
			rows = json.loads(raw)
		except Exception as e:  # noqa: BLE001
			record(f"bi:fixture_parses:{label}", False, f"{type(e).__name__}: {e}")
			continue
		record(f"bi:fixture_parses:{label}", isinstance(rows, list), f"{type(rows).__name__}")
		if not isinstance(rows, list):
			continue

		# At least one row, all FClist/FCLists-prefixed (scoped to OUR fixtures — never a foreign app's rows).
		names = [str(r.get("name", "")) for r in rows if isinstance(r, dict)]
		prefixed = bool(names) and all(n.startswith("FClist") or n.startswith("FCLists") for n in names)
		record(f"bi:fixture_scoped:{label}", prefixed,
			f"{len(names)} row(s): {', '.join(names) if names else 'none'}")

		# ON-SITE proof (S033 failure mode): each fixture row must actually EXIST as a doc on the site —
		# a fixture that only lives as JSON (failed/never-run sync) is a shipped-but-dead shell.
		for name in names:
			record(f"bi:on_site:{label}:{name}", bool(frappe.db.exists(label, name)),
				"exists on site" if frappe.db.exists(label, name) else "MISSING on site (fixture not synced)")

		# No Frappe Insights / foreign-BI app referenced anywhere in the fixture JSON text.
		hit = next((tok for tok in FORBIDDEN_BI_TOKENS if tok in raw), None)
		record(f"bi:fixture_native_only:{label}", hit is None,
			"native frappe BI only" if hit is None else f"foreign BI token: {hit}")

	# ----------------------------------------------------------------------------------------------
	# (4) DEPENDENCY HYGIENE — required_apps == ["erpnext"] and no forbidden imports/literals in tree.
	# ----------------------------------------------------------------------------------------------
	required = frappe.get_hooks("required_apps", app_name="fclists") or []
	# get_hooks may return the list flattened; normalise to a plain sorted list of app names.
	required_norm = sorted({str(a).strip() for a in required if a})
	record("deps:required_apps", required_norm == ["erpnext"], f"required_apps={required_norm}")

	# Grep the whole app tree for forbidden app imports and client literals.
	import_hits = []
	literal_hits = []
	# Precompiled patterns: `import X`, `from X`, or dotted use `X.` for each forbidden app.
	forbidden_patterns = {
		app: re.compile(r"(?:^|[^\w.])(?:import\s+%s|from\s+%s|%s\.)" % (re.escape(app), re.escape(app), re.escape(app)))
		for app in FORBIDDEN_APPS
	}
	scan_exts = (".py", ".js", ".json", ".vue", ".ts", ".txt", ".md", ".cfg", ".toml")
	skip_dirs = {"__pycache__", ".git", "node_modules", "dist", "build"}
	repo_root = os.path.dirname(app_path)  # …/apps/fclists (repo root, one level above module dir)

	for base, dirs, files in os.walk(repo_root):
		dirs[:] = [d for d in dirs if d not in skip_dirs]
		for fname in files:
			if not fname.endswith(scan_exts):
				continue
			# Never flag THIS verifier (it legitimately names the forbidden apps to check for them).
			if fname == "_verify_fclists.py":
				continue
			fpath = os.path.join(base, fname)
			text = _read(fpath)
			if text is None:
				continue
			rel = os.path.relpath(fpath, repo_root)
			for app, pat in forbidden_patterns.items():
				if pat.search(text):
					import_hits.append(f"{rel}:{app}")
			for lit in FORBIDDEN_LITERALS:
				if lit in text:
					literal_hits.append(f"{rel}:{lit}")

	record("deps:no_forbidden_imports", len(import_hits) == 0,
		"clean" if not import_hits else "; ".join(sorted(set(import_hits))))
	record("deps:no_client_literals", len(literal_hits) == 0,
		"clean" if not literal_hits else "; ".join(sorted(set(literal_hits))))

	# ----------------------------------------------------------------------------------------------
	# (5) SECURITY DENY + ALLOW-AS-PERSONA + (6) USER-PERMISSION SCOPING — (3) proves each report
	# executes as Administrator; here prove each DENY, that each report ALSO runs for a single admitted
	# non-admin role (5c — Administrator-only execution masks dead role tables), and the row scope.
	# Self-seeded neutral fixture; torn down in the finally. sw/testing.md §2: no half-tests.
	# ----------------------------------------------------------------------------------------------
	session_user = frappe.session.user
	try:
		frappe.set_user("Administrator")

		# --- (5a) role-less user is REFUSED by the runner on a gated Accounts AND Stock report --------
		_ensure_user(DENY_USER, "FCLists Verify NoRoles", [])
		frappe.set_user(DENY_USER)
		for rname in ("FClist GL", "FClist Item Stock"):
			denied, detail = False, "runner returned data (NO refusal)"
			try:
				run_report(rname, filters={})
			except frappe.PermissionError as e:
				denied, detail = True, f"PermissionError: {str(e)[:80]}"
			except Exception as e:  # noqa: BLE001 — wrong refusal type is a FAIL, not a pass
				detail = f"{type(e).__name__}: {str(e)[:80]}"
			record(f"deny:roleless_run_report:{rname}", denied, detail)
		frappe.set_user("Administrator")

		# --- (5b) guide gate: Guest + role-less REFUSED, Administrator renders ------------------------
		guide = importlib.import_module("fclists.www.fclists-guide")
		for label, guide_user in (("guest", "Guest"), ("roleless", DENY_USER)):
			frappe.set_user(guide_user)
			raised, detail = False, "get_context rendered (NO refusal)"
			try:
				guide.get_context(frappe._dict())
			except frappe.PermissionError as e:
				raised, detail = True, f"PermissionError: {str(e)[:80]}"
			except Exception as e:  # noqa: BLE001
				detail = f"{type(e).__name__}: {str(e)[:80]}"
			record(f"deny:guide:{label}", raised, detail)
			frappe.set_user("Administrator")
		ctx = frappe._dict()
		guide.get_context(ctx)
		record("allow:guide_admin", ctx.get("title") == "FCLists — User Guide",
			f"title={ctx.get('title')}")

		# --- (5c) ALLOW-AS-PERSONA: every report must RUN for a user holding exactly ONE of the roles
		# its Report doc admits (non-admin, so the check can never pass via System Manager's blanket
		# access). This catches role tables that admit only DEAD roles — e.g. a ref_doctype whose
		# 'report' permission is never granted to the admitted role, or a child-table ref_doctype for
		# which has_permission(..., 'report') refuses every non-Administrator. Section 3's Administrator
		# execution alone would mask all of those.
		for rname in REPORTS:
			if not frappe.db.exists("Report", rname):
				record(f"allow:persona_run_report:{rname}", False, "report missing on site")
				continue
			admitted = [r.role for r in frappe.get_doc("Report", rname).roles]
			non_admin = [r for r in admitted if r not in ("Administrator", "System Manager")]
			persona = (non_admin or admitted or [None])[0]
			if not persona:
				record(f"allow:persona_run_report:{rname}", False, "no roles on the Report doc")
				continue
			_ensure_user(ALLOW_USER, "FCLists Verify Persona", [persona])
			frappe.set_user(ALLOW_USER)
			ok, detail = False, ""
			try:
				res = run_report(rname, filters={})
				cols = res.get("columns") if isinstance(res, dict) else None
				ok = bool(cols) and isinstance(res.get("result"), list)
				detail = f"as {persona}: cols={bool(cols)}"
			except Exception as e:  # noqa: BLE001 — a refused admitted persona is exactly the RED we want
				detail = f"as {persona}: {type(e).__name__}: {str(e)[:120]}"
			finally:
				frappe.set_user("Administrator")
			record(f"allow:persona_run_report:{rname}", ok, detail)

		# --- (6) User-Permission scoping: Alpha-locked Accounts User never sees Beta rows --------------
		_ensure_company(COMPANY_ALPHA, ABBR_ALPHA)
		_ensure_company(COMPANY_BETA, ABBR_BETA)
		_ensure_user(SCOPED_USER, "FCLists Verify Scoped", ["Accounts User"])
		if not frappe.db.exists("User Permission",
				{"user": SCOPED_USER, "allow": "Company", "for_value": COMPANY_ALPHA}):
			frappe.get_doc({
				"doctype": "User Permission",
				"user": SCOPED_USER,
				"allow": "Company",
				"for_value": COMPANY_ALPHA,
				"apply_to_all_doctypes": 1,
			}).insert(ignore_permissions=True)
		frappe.clear_cache(user=SCOPED_USER)

		def _account_rows(filters=None):
			res = run_report("FClist Account", filters=filters or {})
			return [r for r in (res.get("result") or []) if isinstance(r, dict)]

		# Baseline as Administrator: BOTH companies' auto-created accounts render — proves the Beta rows
		# EXIST on the site, so the scoped DENY below can never pass vacuously.
		names_admin = [str(r.get("name") or "") for r in _account_rows()]
		admin_alpha = any(n.endswith(" - " + ABBR_ALPHA) for n in names_admin)
		admin_beta = any(n.endswith(" - " + ABBR_BETA) for n in names_admin)
		record("scope:admin_sees_both_companies", admin_alpha and admin_beta,
			f"alpha={admin_alpha} beta={admin_beta} ({len(names_admin)} rows)")

		frappe.set_user(SCOPED_USER)
		names_scoped = [str(r.get("name") or "") for r in _account_rows()]
		record("scope:scoped_sees_alpha",
			any(n.endswith(" - " + ABBR_ALPHA) for n in names_scoped),
			f"{len(names_scoped)} rows visible to the scoped user")
		beta_leaks = [n for n in names_scoped if n.endswith(" - " + ABBR_BETA)]
		record("scope:scoped_never_sees_beta", not beta_leaks,
			"no Beta row leaked" if not beta_leaks else f"LEAKED: {', '.join(beta_leaks[:5])}")
		# Explicitly requesting the forbidden company must yield ZERO rows (volume-independent proof —
		# the User Permission ANDs with the filter, so no site growth can mask a leak).
		beta_filtered = _account_rows({"company": COMPANY_BETA})
		record("scope:beta_filter_returns_nothing", len(beta_filtered) == 0,
			f"{len(beta_filtered)} rows for an explicit Beta filter")
	except Exception as e:  # noqa: BLE001 — a crashed security section is a RED, never a silent skip
		record("security:section_crashed", False, f"{type(e).__name__}: {str(e)[:200]}")
	finally:
		try:
			_teardown_security_fixture()
		except Exception as e:  # noqa: BLE001
			record("security:teardown_failed", False, f"{type(e).__name__}: {str(e)[:200]}")
		frappe.set_user(session_user if session_user else "Administrator")

	# ----------------------------------------------------------------------------------------------
	# (7) SHELL FIXTURES ON SITE — the Workspace / Sidebar / Desktop Icon must exist as DOCS (the BI
	# fixtures are asserted on-site row-by-row in (3b) above). JSON-on-disk alone = dead shell (S033).
	# ----------------------------------------------------------------------------------------------
	record("shell:workspace_on_site", bool(frappe.db.exists("Workspace", "FCLists")),
		"Workspace 'FCLists'")
	record("shell:sidebar_on_site", bool(frappe.db.exists("Workspace Sidebar", "FCLists")),
		"Workspace Sidebar 'FCLists'")
	# Desktop Icon autonames by label — match by app so either naming lands.
	record("shell:desktop_icon_on_site", bool(frappe.db.exists("Desktop Icon", {"app": "fclists"})),
		"Desktop Icon app=fclists")

	# ----------------------------------------------------------------------------------------------
	# (8) REPORT-PERIOD PRESET FILTER — the QuickBooks-style "Report period" dropdown (yokoten of
	# fcreports/fcreports/periods.py). Client-side registry/resolver present + wired into every report
	# with a from_date/to_date pair; server-side fiscal companion present, whitelisted, and executes.
	# ----------------------------------------------------------------------------------------------
	periods_js_path = os.path.join(app_path, "public", "js", "fclists_periods.js")
	periods_js_src = _read(periods_js_path)
	record("periods:js_exists", periods_js_src is not None, "public/js/fclists_periods.js")
	if periods_js_src is not None:
		record("periods:js_defines_periods", "fclists.periods.PERIODS = [" in periods_js_src,
			"defines fclists.periods.PERIODS")
		record("periods:js_defines_resolve", "fclists.periods.resolve = function" in periods_js_src,
			"defines fclists.periods.resolve")
		record("periods:js_defines_filter_def", "fclists.periods.filter_def = function" in periods_js_src,
			"defines fclists.periods.filter_def")

	include_js = frappe.get_hooks("app_include_js", app_name="fclists") or []
	record("periods:hooked_app_include_js",
		any("fclists_periods.js" in str(p) for p in include_js),
		f"app_include_js={list(include_js)}")

	# Server-side fiscal companion — present on disk, whitelisted, and genuinely executes for BOTH fiscal
	# keys (falling back to the calendar equivalent when no Fiscal Year is configured — never a crash),
	# while an unknown key is rejected rather than silently resolved.
	try:
		periods_mod = importlib.import_module("fclists.periods")
		record("periods:py_module_imports", True, "fclists.periods imports")
		fn = getattr(periods_mod, "resolve_fiscal_period", None)
		record("periods:py_defines_resolve_fiscal", callable(fn), "resolve_fiscal_period is callable")
		is_wl = bool(fn and fn in frappe.whitelisted)
		record("periods:py_resolve_fiscal_whitelisted", is_wl,
			f"in frappe.whitelisted={is_wl}" if fn else "resolve_fiscal_period missing")
		if fn:
			for key in ("next_fiscal_quarter", "next_financial_year"):
				try:
					result = fn(key)
					ok = (
						isinstance(result, dict)
						and bool(result.get("from_date"))
						and bool(result.get("to_date"))
					)
					record(f"periods:py_resolves:{key}", ok, str(result))
				except Exception as e:  # noqa: BLE001
					record(f"periods:py_resolves:{key}", False, f"{type(e).__name__}: {e}")
			try:
				bad = fn("not_a_real_key")
				record("periods:py_rejects_unknown_key", bad is None, f"got {bad!r} for an unknown key")
			except Exception as e:  # noqa: BLE001
				record("periods:py_rejects_unknown_key", False, f"{type(e).__name__}: {e}")
	except Exception as e:  # noqa: BLE001
		record("periods:py_module_imports", False, f"{type(e).__name__}: {e}")

	# Every report with a from_date/to_date pair must ALSO splice fclists.periods.filter_def() into its
	# filters array — a source-scan so a future date-range report can never silently skip the preset.
	for rname, relpath in sorted(DATE_RANGE_REPORT_JS.items()):
		fpath = os.path.join(app_path, relpath.replace("/", os.sep))
		src = _read(fpath)
		record(f"periods:report_file_exists:{rname}", src is not None, relpath)
		if src is None:
			continue
		record(f"periods:report_wired:{rname}", "fclists.periods.filter_def(" in src,
			"fclists.periods.filter_def(" if "fclists.periods.filter_def(" in src else "NOT wired")

	# ----------------------------------------------------------------------------------------------
	# (9) TREE-CHECKBOX COMPANY FILTER (2026-07-17 yokoten of the fcbi/fcbi/consolidate.py pattern via
	# fclists.nav_options — see that module's docstring for the full pattern-source citation). Confines-
	# not-expands proof on FClist GL (the simplest of the 9 upgraded reports — a straight GL Entry
	# `company IN (...)` filter, no join): the unfiltered run must return MORE THAN ZERO rows (else the
	# "filtered <= unfiltered" inequality would pass vacuously on an empty site), and filtering to a
	# single real Company via the NEW `companies` MultiSelectList list-arg must return a row count that is
	# both > 0 and <= the unfiltered count — never more (a filter that let MORE rows through would be a
	# broken WHERE clause, not a working confinement). Read-only; no fixture seeded/torn down (borrows
	# whatever real Company already exists on the site — this app's own CLAUDE.md requires at least one).
	# ----------------------------------------------------------------------------------------------
	try:
		probe_company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		if not probe_company:
			record("companies_filter:gl_confines", False, "no Company exists on this site to probe with")
		else:
			unfiltered = run_report("FClist GL", filters={})
			unfiltered_rows = unfiltered.get("result") if isinstance(unfiltered, dict) else None
			unfiltered_n = len(unfiltered_rows) if isinstance(unfiltered_rows, list) else 0
			record("companies_filter:gl_unfiltered_nonempty", unfiltered_n > 0,
				f"{unfiltered_n} unfiltered GL row(s) (probe company={probe_company})")

			filtered = run_report("FClist GL", filters={"companies": [probe_company]})
			filtered_rows = filtered.get("result") if isinstance(filtered, dict) else None
			filtered_n = len(filtered_rows) if isinstance(filtered_rows, list) else 0
			record("companies_filter:gl_filtered_nonempty", filtered_n > 0,
				f"{filtered_n} row(s) for companies=[{probe_company}]")
			record("companies_filter:gl_confines", filtered_n <= unfiltered_n,
				f"filtered={filtered_n} <= unfiltered={unfiltered_n}")
	except Exception as e:  # noqa: BLE001
		record("companies_filter:gl_confines", False, f"{type(e).__name__}: {e}")

	# --- (9b) Wave-2 companies-leg: FClist Stock Movement (a report upgraded THIS wave, joined straight
	# onto Stock Ledger Entry.company — no Warehouse join needed) must also CONFINE, never expand, under
	# the same `companies` MultiSelectList list-arg. Same vacuity guard as 9's GL proof (unfiltered must be
	# non-empty first) so "filtered <= unfiltered" can never pass on an empty site.
	try:
		probe_company_sm = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		if not probe_company_sm:
			record("companies_filter:stock_movement_confines", False,
				"no Company exists on this site to probe with")
		else:
			unfiltered = run_report("FClist Stock Movement", filters={})
			unfiltered_rows = unfiltered.get("result") if isinstance(unfiltered, dict) else None
			unfiltered_n = len(unfiltered_rows) if isinstance(unfiltered_rows, list) else 0
			record("companies_filter:stock_movement_unfiltered_nonempty", unfiltered_n > 0,
				f"{unfiltered_n} unfiltered Stock Movement row(s) (probe company={probe_company_sm})")

			filtered = run_report("FClist Stock Movement", filters={"companies": [probe_company_sm]})
			filtered_rows = filtered.get("result") if isinstance(filtered, dict) else None
			filtered_n = len(filtered_rows) if isinstance(filtered_rows, list) else 0
			record("companies_filter:stock_movement_confines", filtered_n <= unfiltered_n,
				f"filtered={filtered_n} <= unfiltered={unfiltered_n}")
	except Exception as e:  # noqa: BLE001
		record("companies_filter:stock_movement_confines", False, f"{type(e).__name__}: {e}")

	# --- (9c) Wave-2 cost_center-leg: FClist Payments — Payment Entry DOES carry a header cost_center
	# field (the bench fact that overturned this report's wave-1 exclusion), so prove the NEW `cost_center`
	# MultiSelectList list-arg also CONFINES. Unlike 9/9b, a real site may legitimately have ZERO Payment
	# Entries stamped against the probe Cost Centre (cost_center is optional on Payment Entry) — that is
	# NOT a defect, so this leg does NOT assert filtered-nonempty; it only asserts the confinement
	# inequality and records the vacuous case honestly in the detail string rather than masking it.
	# ----------------------------------------------------------------------------------------------
	try:
		probe_cc = frappe.db.get_value("Cost Center", {}, "name", order_by="creation asc")
		if not probe_cc:
			record("cost_center_filter:payments_confines", False,
				"no Cost Center exists on this site to probe with")
		else:
			unfiltered = run_report("FClist Payments", filters={})
			unfiltered_rows = unfiltered.get("result") if isinstance(unfiltered, dict) else None
			unfiltered_n = len(unfiltered_rows) if isinstance(unfiltered_rows, list) else 0
			record("cost_center_filter:payments_unfiltered_nonempty", unfiltered_n > 0,
				f"{unfiltered_n} unfiltered Payments row(s) (probe cost center={probe_cc})")

			filtered = run_report("FClist Payments", filters={"cost_center": [probe_cc]})
			filtered_rows = filtered.get("result") if isinstance(filtered, dict) else None
			filtered_n = len(filtered_rows) if isinstance(filtered_rows, list) else 0
			vacuous_note = (
				"" if filtered_n > 0 else
				" (0 rows — no Payment Entry on this site carries this cost centre;"
				" confinement still holds vacuously, honestly noted rather than masked)"
			)
			record("cost_center_filter:payments_confines", filtered_n <= unfiltered_n,
				f"filtered={filtered_n} <= unfiltered={unfiltered_n}{vacuous_note}")
	except Exception as e:  # noqa: BLE001
		record("cost_center_filter:payments_confines", False, f"{type(e).__name__}: {e}")

	# ----------------------------------------------------------------------------------------------
	# Roll-up + numbered PASS/FAIL print.
	# ----------------------------------------------------------------------------------------------
	total = len(checks)
	passed = sum(1 for c in checks if c["ok"])
	all_ok = passed == total

	print("=" * 88)
	print("FCLists live verifier — group.localhost")
	print("=" * 88)
	for i, c in enumerate(checks, 1):
		status = "PASS" if c["ok"] else "FAIL"
		print(f"{i:>3}. [{status}] {c['check']}  ::  {c['detail']}")
	print("-" * 88)
	print(f"{passed}/{total}")
	print(f"all_ok: {str(all_ok).lower()}")
	print("=" * 88)

	result = {"all_ok": all_ok, "passed": passed, "total": total, "count": f"{passed}/{total}"}
	if not all_ok:
		result["failures"] = [c for c in checks if not c["ok"]]
	return result
