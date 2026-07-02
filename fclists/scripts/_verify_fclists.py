"""FCLists live VERIFIER (D-042 parity sweep — modelled on fcduka/fcduka/api/_verify_fclists.py).

Proves, on a real site (group.localhost), that the FCLists surface is wired correctly and stays
sector-neutral + config-not-fork + upgrade-safe. Four families of checks:

  (1) LIST-JS WIRING (Finding A) — every doctype_list_js entry in fclists/hooks.py resolves to a real
      file on disk that EXTENDS the native listview via `fclists.extend_listview(` and NOT via a bare
      `frappe.listview_settings["X"] = {` reassignment (Frappe concatenates every app's list-js; a bare
      assignment clobbers ERPNext's native config for the doctype).
  (2) LOADER PRIMITIVE — public/js/fclists_lib.js exists and DEFINES `fclists.extend_listview` (the merge
      -and-chain helper that (1) depends on).
  (3) REPORT SECURITY + EXECUTION (Finding B) — every Wave-1 report exists as a Script Report with a
      ref_doctype, is ROLE-GATED (non-empty roles — never world-readable), and actually EXECUTES + renders
      through frappe's own runner `frappe.desk.query_report.run` (the identical path CSV/print export use).
  (4) DEPENDENCY HYGIENE — required_apps == ["erpnext"] EXACTLY, and NO fclists source file imports
      flowcore / fcduka / titan_mpsa / titan / settle / leanorg (grep the whole tree).

Self-contained, idempotent, read-only (never writes/commits/migrates). Prints a numbered PASS/FAIL per
check, a rolled-up "N/N", and a final "all_ok: true/false".

Run:  bench --site group.localhost execute fclists.scripts._verify_fclists.run
"""

import os
import re

import frappe
from frappe.desk.query_report import run as run_report

# Wave-1 reports, referenced by DISPLAY NAME (exactly as declared in each report JSON's report_name).
REPORTS = [
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

# Apps that fclists must NEVER import or depend on (single-owner / config-not-fork law). erpnext is the
# only permitted dependency. Matched as `import X` / `from X` and dotted-attribute use `X.` in source.
FORBIDDEN_APPS = ["flowcore", "fcduka", "titan_mpsa", "titan", "settle", "leanorg"]

# Client literals that must never appear in fclists source (sector-neutral, config-driven — D-002/D-024).
FORBIDDEN_LITERALS = ["Vets", "Agrovet", "Busara", "Diamante"]


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
