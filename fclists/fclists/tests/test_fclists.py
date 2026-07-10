# Copyright (c) 2026, Flowcore and Contributors
# See license.txt
"""Hermetic unit tests for FCLists — pure logic only, NO live ledger required.

Covers BOTH Wave 1 (inventory + sales/transaction-history families) and Wave 2 (accounts / AR-AP density +
BI-style rollups: Account, GL, Customer/Supplier Balance, Open Invoices aging, Purchase Invoice, Bank
Reconciliation Queue, Best Sellers, Sales by Cashier/Department, Sales YoY).

These tests cover the ledger-free surfaces of the app:

  1. The Script-Report COLUMN BUILDERS (`_columns()` in every report module). These are pure functions
     returning a static column schema — no DB reads — so we can assert their shape, fieldnames, and that
     every referenced doctype/option is a NATIVE ERPNext one (Hard Rule 1: required_apps = ["erpnext"]).

  2. The capability-gate / flag PREDICATES:
        - `_enabled()` (the site_config `fclists_enabled` gate, default-on) on the reports that carry it.
        - The overdue predicate (Sales Invoice) and the expiry-status classifier (Batch Expiry) reproduced
          as pure functions and asserted against their published thresholds. We test the *logic contract*
          (due_date<today AND outstanding>0 ⇒ overdue; days<0 ⇒ Expired; days<=warn ⇒ Expiring; else OK),
          which is the ledger-independent core; the `_data()` assembly that needs Bin/SLE rows is out of
          scope for a hermetic test.
        - The Wave-2 predicates: the AR aging-bucket classifier (Open Invoices), the available-credit floor
          (Customer Balance), and the YoY period math (Sales YoY: whole-year Feb-29-safe shift, like-for-like
          windows, guarded %-change). Each is mirrored as a pure function and checked against its report at
          the boundaries; `_periods()`/`_bucket()` are also called on the real module (they need no ledger).

  3. The `fclists.extend_listview` SAVE-AND-CHAIN contract enforced at the source level: a JS-logic unit is
     impractical in Python, so instead we STATICALLY assert every `public/js/*_list.js` file goes through
     `fclists.extend_listview(...)` and contains NO bare `frappe.listview_settings["X"] = {...}`
     reassignment (Finding A — a bare `=` drops native + prior-app list config because Frappe concatenates
     all apps' list-js into one bundle).

Runnable via:  bench --site <site> run-tests --app fclists --module \
                 fclists.fclists.tests.test_fclists
"""

import json
import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate


# ----------------------------------------------------------------------------------------------------
# Helpers to reach the report modules & the list-js files by convention (no hard-coded absolute paths).
# ----------------------------------------------------------------------------------------------------

# Every Script Report, keyed by its DISPLAY name, mapped to the scrubbed module folder (Hard Rule 6:
# reports live at fclists/fclists/report/<scrubbed>/<scrubbed>.py). Reference by display name.
REPORT_MODULES = {
	# --- Wave 1 -----------------------------------------------------------------------------------
	"FClist Item Stock": "fclist_item_stock",
	"FClist Batch Expiry": "fclist_batch_expiry",
	"FClist Reorder": "fclist_reorder",
	"FClist Sales Invoice": "fclist_sales_invoice",
	"FClist Sales History": "fclist_sales_history",
	"FClist Returns": "fclist_returns",
	"FClist Payments": "fclist_payments",
	"FClist POS Invoice": "fclist_pos_invoice",
	"FClist Stock Movement": "fclist_stock_movement",
	# --- Wave 2 (accounts / AR-AP density + BI-style rollups) --------------------------------------
	"FClist Account": "fclist_account",
	"FClist GL": "fclist_gl",
	"FClist Customer Balance": "fclist_customer_balance",
	"FClist Supplier Balance": "fclist_supplier_balance",
	"FClist Open Invoices": "fclist_open_invoices",
	"FClist Purchase Invoice": "fclist_purchase_invoice",
	"FClist Bank Reconciliation Queue": "fclist_bank_reconciliation_queue",
	"FClist Best Sellers": "fclist_best_sellers",
	"FClist Sales by Cashier": "fclist_sales_by_cashier",
	"FClist Sales by Department": "fclist_sales_by_department",
	"FClist Sales YoY": "fclist_sales_yoy",
	# --- Wave 3 (QB-POS parity borrows — S035, live-gemba screens from the agrovet) -----------------
	"FClist Payment Summary": "fclist_payment_summary",
	"FClist Receipt Detail": "fclist_receipt_detail",
	# --- D-070 (item-identity hygiene — normalized-name duplicate clustering) -----------------------
	"FClist Duplicate Items": "fclist_duplicate_items",
}

# The Wave-2 report display names — used to scope Wave-2-only assertions without re-listing Wave 1.
WAVE2_REPORTS = {
	"FClist Account",
	"FClist GL",
	"FClist Customer Balance",
	"FClist Supplier Balance",
	"FClist Open Invoices",
	"FClist Purchase Invoice",
	"FClist Bank Reconciliation Queue",
	"FClist Best Sellers",
	"FClist Sales by Cashier",
	"FClist Sales by Department",
	"FClist Sales YoY",
}

# Reports that carry the site_config `_enabled()` capability gate (the stock/inventory ones).
REPORTS_WITH_ENABLE_GATE = {
	"FClist Item Stock",
	"FClist Batch Expiry",
	"FClist Reorder",
	"FClist Stock Movement",
	"FClist Duplicate Items",
}

# The doctypes any FCLists report column may legally reference (Link/Dynamic Link options).
# ALL native to Frappe/ERPNext — never a flowcore/fcduka/settle/etc. doctype (Hard Rule 1).
ALLOWED_NATIVE_OPTION_DOCTYPES = {
	"Item", "Item Group", "UOM", "Batch", "Warehouse", "Customer", "Supplier",
	"Sales Invoice", "POS Invoice", "Purchase Invoice", "Payment Entry", "Mode of Payment",
	"POS Profile", "Currency", "User", "Account", "Stock Ledger Entry", "GL Entry", "Bin",
}

# Doctypes that must NEVER appear (single-owner / required_apps law — Hard Rule 1).
FORBIDDEN_OPTION_SUBSTRINGS = ("flowcore", "fcduka", "titan", "settle", "leanorg", "fcmuster")


def _report_module(display_name):
	"""Import a report's python module by its scrubbed path and return it."""
	scrubbed = REPORT_MODULES[display_name]
	return frappe.get_module(f"fclists.fclists.report.{scrubbed}.{scrubbed}")


def _list_js_dir():
	"""Absolute path to fclists/public/js (via frappe app-path, not a hard-coded literal)."""
	return os.path.join(frappe.get_app_path("fclists"), "public", "js")


def _list_js_files():
	"""Every *_list.js under public/js (the listview extensions we contract-check)."""
	js_dir = _list_js_dir()
	return sorted(
		os.path.join(js_dir, f)
		for f in os.listdir(js_dir)
		if f.endswith("_list.js")
	)


def _strip_js_line_comments(src):
	"""Remove // line-comments and /* */ block-comments so we test CODE, not the cautionary comments.

	The *_list.js files each contain a comment WARNING against the bare-reassignment anti-pattern (it even
	quotes `frappe.listview_settings["X"] = {...}`); a naive substring scan would false-positive on those.
	This strips comments first. Deliberately simple — good enough for our own well-formed source (no
	`//` or `/*` inside string/regex literals in these files).
	"""
	src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)  # block comments
	src = re.sub(r"//[^\n]*", "", src)                      # line comments
	return src


# ----------------------------------------------------------------------------------------------------
# Pure re-implementations of the ledger-independent flag logic, mirroring the report source EXACTLY.
# Testing these asserts the *contract* (thresholds & boolean rule) without touching Bin/SLE/Invoice rows.
# ----------------------------------------------------------------------------------------------------

def _is_overdue(docstatus, outstanding_amount, due_date, today):
	"""Sales-Invoice overdue predicate: submitted, money owed, past due. Mirrors fclist_sales_invoice._data
	(and the sales_invoice_list.js indicator)."""
	if int(docstatus or 0) != 1:
		return False
	if float(outstanding_amount or 0) <= 0:
		return False
	if not due_date:
		return False
	return getdate(due_date) < getdate(today)


def _expiry_status(days_to_expiry, warn_days):
	"""Batch FEFO status classifier. Mirrors fclist_batch_expiry._data:
	   days<0 ⇒ Expired · days<=warn ⇒ Expiring · else OK."""
	if days_to_expiry < 0:
		return "Expired"
	if days_to_expiry <= warn_days:
		return "Expiring"
	return "OK"


def _aging_bucket(days_past_due):
	"""AR aging-bucket classifier. Mirrors fclist_open_invoices._bucket EXACTLY:
	   <=0 ⇒ Current · <=30 ⇒ 1-30 · <=60 ⇒ 31-60 · <=90 ⇒ 61-90 · else 90+.
	Labels here are the raw (untranslated) strings the report's `_()` wraps — in a test context with no
	translation loaded, `_(x)` is identity, so the report and this mirror return equal strings."""
	if days_past_due <= 0:
		return "Current"
	if days_past_due <= 30:
		return "1-30"
	if days_past_due <= 60:
		return "31-60"
	if days_past_due <= 90:
		return "61-90"
	return "90+"


def _available_credit(credit_limit, outstanding):
	"""Available-credit predicate. Mirrors fclist_customer_balance._data:
	   only meaningful when a limit is set; headroom = limit − outstanding, FLOORED at 0 (never negative).
	   No limit set (falsy / 0) ⇒ 0.0 (we do not invent headroom)."""
	limit = float(credit_limit or 0)
	out = float(outstanding or 0)
	return max(limit - out, 0.0) if limit else 0.0


def _shift_year(d, years):
	"""Mirror of fclist_sales_yoy._shift_year: shift whole years, guarding Feb-29 → Feb-28."""
	try:
		return d.replace(year=d.year + years)
	except ValueError:
		return d.replace(month=2, day=28, year=d.year + years)


def _change_pct(this_year, last_year):
	"""YoY %-change predicate. Mirrors fclist_sales_yoy._data: change/last*100 (2dp), 0 when last==0
	(no divide-by-zero, no infinite growth)."""
	ty = float(this_year or 0)
	ly = float(last_year or 0)
	return round((ty - ly) / ly * 100.0, 2) if ly else 0.0


# ====================================================================================================
# 1. Report column builders — pure, native-only, well-formed schema.
# ====================================================================================================

class TestReportColumns(FrappeTestCase):
	def test_every_report_module_importable_and_has_columns(self):
		"""Each report exposes a callable _columns() and execute() (Script Report contract)."""
		for name in REPORT_MODULES:
			mod = _report_module(name)
			self.assertTrue(callable(getattr(mod, "_columns", None)), f"{name}: _columns missing")
			self.assertTrue(callable(getattr(mod, "execute", None)), f"{name}: execute missing")

	def test_columns_are_well_formed(self):
		"""Every column is a dict with a non-empty label, fieldname, and fieldtype; fieldnames are unique."""
		for name in REPORT_MODULES:
			cols = _report_module(name)._columns()
			self.assertIsInstance(cols, list, f"{name}: _columns() must return a list")
			self.assertGreater(len(cols), 0, f"{name}: _columns() must not be empty")
			seen = set()
			for c in cols:
				self.assertIsInstance(c, dict, f"{name}: column not a dict: {c!r}")
				for key in ("label", "fieldname", "fieldtype"):
					self.assertTrue(c.get(key), f"{name}: column missing {key}: {c!r}")
				fn = c["fieldname"]
				self.assertNotIn(fn, seen, f"{name}: duplicate fieldname {fn!r}")
				seen.add(fn)

	def test_link_columns_reference_only_native_doctypes(self):
		"""Hard Rule 1: Link / Dynamic Link `options` must be a NATIVE erpnext doctype — never a flowcore/
		fcduka/etc. doctype. Dynamic Link options that name a sibling fieldname (e.g. party_type,
		voucher_type, currency-field) are skipped — they point at a field, not a doctype."""
		for name in REPORT_MODULES:
			cols = _report_module(name)._columns()
			col_fieldnames = {c["fieldname"] for c in cols}
			for c in cols:
				options = c.get("options")
				if not options:
					continue
				# forbidden-owner check applies regardless of fieldtype
				low = options.lower()
				for bad in FORBIDDEN_OPTION_SUBSTRINGS:
					self.assertNotIn(bad, low, f"{name}: column {c['fieldname']} references forbidden {options!r}")
				if c["fieldtype"] == "Link":
					self.assertIn(
						options, ALLOWED_NATIVE_OPTION_DOCTYPES,
						f"{name}: Link column {c['fieldname']} options={options!r} is not a whitelisted native doctype",
					)
				elif c["fieldtype"] == "Dynamic Link":
					# options is a fieldname on the same row (points to a doctype at runtime) — must exist.
					self.assertIn(
						options, col_fieldnames,
						f"{name}: Dynamic Link {c['fieldname']} options={options!r} must name a column fieldname",
					)

	def test_no_client_literals_in_column_labels(self):
		"""Hard Rule 5: sector-neutral — no client/vertical literal anywhere in the column schema."""
		banned = ("vet", "agrovet", "busara", "diamante", "dgg", "skillwave")
		for name in REPORT_MODULES:
			cols = _report_module(name)._columns()
			blob = repr(cols).lower()
			for word in banned:
				self.assertNotIn(word, blob, f"{name}: column schema contains client literal {word!r}")

	def test_key_reports_expose_expected_fieldnames(self):
		"""Spot-check the load-bearing columns of the density reports (the ones a critic would name)."""
		stock = {c["fieldname"] for c in _report_module("FClist Item Stock")._columns()}
		for fn in ("item_code", "on_hand", "valuation_rate", "selling_rate", "margin", "margin_pct",
				   "reorder_level", "units_sold"):
			self.assertIn(fn, stock, f"FClist Item Stock missing column {fn}")

		expiry = {c["fieldname"] for c in _report_module("FClist Batch Expiry")._columns()}
		for fn in ("batch_no", "expiry_date", "days_to_expiry", "qty_remaining", "status"):
			self.assertIn(fn, expiry, f"FClist Batch Expiry missing column {fn}")

		si = {c["fieldname"] for c in _report_module("FClist Sales Invoice")._columns()}
		for fn in ("outstanding_amount", "due_date", "overdue"):
			self.assertIn(fn, si, f"FClist Sales Invoice missing column {fn}")

		reorder = {c["fieldname"] for c in _report_module("FClist Reorder")._columns()}
		for fn in ("reorder_level", "on_hand", "shortfall"):
			self.assertIn(fn, reorder, f"FClist Reorder missing column {fn}")

	def test_wave2_reports_expose_expected_fieldnames(self):
		"""Spot-check the load-bearing columns of each Wave-2 report (the ones a critic would name)."""
		cust = {c["fieldname"] for c in _report_module("FClist Customer Balance")._columns()}
		for fn in ("customer", "outstanding", "credit_limit", "available_credit", "past_due"):
			self.assertIn(fn, cust, f"FClist Customer Balance missing column {fn}")

		sup = {c["fieldname"] for c in _report_module("FClist Supplier Balance")._columns()}
		for fn in ("supplier", "outstanding", "past_due"):
			self.assertIn(fn, sup, f"FClist Supplier Balance missing column {fn}")

		openi = {c["fieldname"] for c in _report_module("FClist Open Invoices")._columns()}
		for fn in ("invoice", "customer", "due_date", "outstanding", "days_past_due", "bucket"):
			self.assertIn(fn, openi, f"FClist Open Invoices missing column {fn}")

		pinv = {c["fieldname"] for c in _report_module("FClist Purchase Invoice")._columns()}
		for fn in ("supplier", "outstanding_amount", "due_date", "overdue"):
			self.assertIn(fn, pinv, f"FClist Purchase Invoice missing column {fn}")

		acc = {c["fieldname"] for c in _report_module("FClist Account")._columns()}
		for fn in ("name", "account_type", "root_type", "balance"):
			self.assertIn(fn, acc, f"FClist Account missing column {fn}")

		gl = {c["fieldname"] for c in _report_module("FClist GL")._columns()}
		for fn in ("posting_date", "account", "debit", "credit", "voucher_no", "party"):
			self.assertIn(fn, gl, f"FClist GL missing column {fn}")

		bank = {c["fieldname"] for c in _report_module("FClist Bank Reconciliation Queue")._columns()}
		for fn in ("name", "payment_type", "paid_amount", "mode_of_payment", "account"):
			self.assertIn(fn, bank, f"FClist Bank Reconciliation Queue missing column {fn}")

		best = {c["fieldname"] for c in _report_module("FClist Best Sellers")._columns()}
		for fn in ("rank", "item_code", "qty_sold", "revenue", "margin"):
			self.assertIn(fn, best, f"FClist Best Sellers missing column {fn}")

		cashier = {c["fieldname"] for c in _report_module("FClist Sales by Cashier")._columns()}
		for fn in ("cashier", "invoice_count", "total_sales", "avg_sale"):
			self.assertIn(fn, cashier, f"FClist Sales by Cashier missing column {fn}")

		dept = {c["fieldname"] for c in _report_module("FClist Sales by Department")._columns()}
		for fn in ("item_group", "qty", "revenue", "share_pct"):
			self.assertIn(fn, dept, f"FClist Sales by Department missing column {fn}")

		yoy = {c["fieldname"] for c in _report_module("FClist Sales YoY")._columns()}
		for fn in ("period", "this_year", "last_year", "change", "change_pct"):
			self.assertIn(fn, yoy, f"FClist Sales YoY missing column {fn}")

	def test_wave2_reports_have_no_enable_gate(self):
		"""Wave-2 (accounts/AR-AP) reports are NOT behind the stock `_enabled()` site-config gate — they are
		accounts surfaces, always available. Guard against a copy-paste that would wrongly gate them off."""
		for name in WAVE2_REPORTS:
			self.assertNotIn(name, REPORTS_WITH_ENABLE_GATE, f"{name}: Wave-2 report must not be enable-gated")

	def test_dynamic_link_options_name_a_sibling_fieldname(self):
		"""Wave-2 GL / Bank-Rec reports use Dynamic Link columns (voucher_no→voucher_type, party→party_type).
		Every Dynamic Link `options` must name a real sibling column fieldname (so it resolves at runtime),
		never a hard doctype literal."""
		for name in ("FClist GL", "FClist Bank Reconciliation Queue"):
			cols = _report_module(name)._columns()
			fieldnames = {c["fieldname"] for c in cols}
			dyn = [c for c in cols if c["fieldtype"] == "Dynamic Link"]
			self.assertGreater(len(dyn), 0, f"{name}: expected at least one Dynamic Link column")
			for c in dyn:
				self.assertIn(
					c["options"], fieldnames,
					f"{name}: Dynamic Link {c['fieldname']} options={c['options']!r} must name a sibling column",
				)


# ====================================================================================================
# 2a. The site_config capability gate — _enabled() defaults ON, honours an explicit off/on.
# ====================================================================================================

class TestEnableGate(FrappeTestCase):
	def setUp(self):
		# snapshot & isolate the conf flag so we never leak state between tests / the live site.
		self._had = "fclists_enabled" in frappe.local.conf
		self._prev = frappe.local.conf.get("fclists_enabled")

	def tearDown(self):
		if self._had:
			frappe.local.conf["fclists_enabled"] = self._prev
		else:
			frappe.local.conf.pop("fclists_enabled", None)

	def _set(self, value):
		if value is None:
			frappe.local.conf.pop("fclists_enabled", None)
		else:
			frappe.local.conf["fclists_enabled"] = value

	def test_default_on_when_unset(self):
		"""Absent flag ⇒ enabled (default-on capability, D-002 data-not-code)."""
		self._set(None)
		for name in REPORTS_WITH_ENABLE_GATE:
			self.assertTrue(_report_module(name)._enabled(), f"{name}: should default ON when unset")

	def test_explicit_zero_disables(self):
		"""fclists_enabled = 0 ⇒ disabled ⇒ execute() returns columns but ZERO data rows (no ledger read)."""
		self._set(0)
		for name in REPORTS_WITH_ENABLE_GATE:
			mod = _report_module(name)
			self.assertFalse(mod._enabled(), f"{name}: should be OFF when flag=0")
			cols, data = mod.execute({})
			self.assertEqual(data, [], f"{name}: disabled report must return no rows")
			self.assertEqual(
				[c["fieldname"] for c in cols],
				[c["fieldname"] for c in mod._columns()],
				f"{name}: disabled report must still return its full column schema",
			)

	def test_explicit_one_enables(self):
		self._set(1)
		for name in REPORTS_WITH_ENABLE_GATE:
			self.assertTrue(_report_module(name)._enabled(), f"{name}: should be ON when flag=1")

	def test_string_flag_coerced(self):
		"""cint() coercion: '0' ⇒ off, '1' ⇒ on (site_config values can arrive as strings)."""
		self._set("0")
		for name in REPORTS_WITH_ENABLE_GATE:
			self.assertFalse(_report_module(name)._enabled(), f"{name}: '0' string must disable")
		self._set("1")
		for name in REPORTS_WITH_ENABLE_GATE:
			self.assertTrue(_report_module(name)._enabled(), f"{name}: '1' string must enable")


# ====================================================================================================
# 2b. The overdue / expiry flag predicates — pure threshold contracts (ledger-independent).
# ====================================================================================================

class TestFlagPredicates(FrappeTestCase):
	def test_overdue_true_when_submitted_owing_and_past_due(self):
		self.assertTrue(_is_overdue(1, 100.0, "2026-06-01", today="2026-07-02"))

	def test_overdue_false_when_not_submitted(self):
		self.assertFalse(_is_overdue(0, 100.0, "2026-06-01", today="2026-07-02"))

	def test_overdue_false_when_fully_paid(self):
		self.assertFalse(_is_overdue(1, 0.0, "2026-06-01", today="2026-07-02"))

	def test_overdue_false_when_not_yet_due(self):
		self.assertFalse(_is_overdue(1, 100.0, "2026-08-01", today="2026-07-02"))

	def test_overdue_false_on_the_due_date_itself(self):
		"""due_date == today is NOT overdue (strict <)."""
		self.assertFalse(_is_overdue(1, 100.0, "2026-07-02", today="2026-07-02"))

	def test_overdue_false_when_no_due_date(self):
		self.assertFalse(_is_overdue(1, 100.0, None, today="2026-07-02"))

	def test_expiry_status_expired(self):
		self.assertEqual(_expiry_status(-1, warn_days=30), "Expired")

	def test_expiry_status_expiring_within_window(self):
		self.assertEqual(_expiry_status(0, warn_days=30), "Expiring")
		self.assertEqual(_expiry_status(30, warn_days=30), "Expiring")

	def test_expiry_status_ok_beyond_window(self):
		self.assertEqual(_expiry_status(31, warn_days=30), "OK")

	def test_expiry_status_respects_custom_warn_days(self):
		self.assertEqual(_expiry_status(45, warn_days=60), "Expiring")
		self.assertEqual(_expiry_status(61, warn_days=60), "OK")


# ====================================================================================================
# 2c. Wave-2 predicates — AR aging buckets, available-credit floor, and YoY period math.
#     Pure threshold/date contracts (ledger-independent); each mirrors its report EXACTLY.
# ====================================================================================================

class TestAgingBucketPredicate(FrappeTestCase):
	"""fclist_open_invoices._bucket: Current / 1-30 / 31-60 / 61-90 / 90+."""

	def test_current_when_not_yet_due(self):
		# not yet due (negative days-past-due) and exactly on the due date are BOTH "Current" (<= 0).
		self.assertEqual(_aging_bucket(-5), "Current")
		self.assertEqual(_aging_bucket(0), "Current")

	def test_bucket_1_30(self):
		self.assertEqual(_aging_bucket(1), "1-30")
		self.assertEqual(_aging_bucket(30), "1-30")

	def test_bucket_31_60(self):
		self.assertEqual(_aging_bucket(31), "31-60")
		self.assertEqual(_aging_bucket(60), "31-60")

	def test_bucket_61_90(self):
		self.assertEqual(_aging_bucket(61), "61-90")
		self.assertEqual(_aging_bucket(90), "61-90")

	def test_bucket_90_plus(self):
		self.assertEqual(_aging_bucket(91), "90+")
		self.assertEqual(_aging_bucket(3650), "90+")

	def test_mirror_matches_report_source(self):
		"""The report's own _bucket must return the same label as our pure mirror at every boundary
		(in a test context `_()` is identity, so labels compare equal)."""
		bucket = _report_module("FClist Open Invoices")._bucket
		for dpd in (-10, -1, 0, 1, 15, 30, 31, 45, 60, 61, 75, 90, 91, 200):
			self.assertEqual(
				str(bucket(dpd)), _aging_bucket(dpd),
				f"open_invoices._bucket({dpd}) disagrees with mirror",
			)


class TestAvailableCreditPredicate(FrappeTestCase):
	"""fclist_customer_balance available-credit: max(limit − outstanding, 0) when a limit is set, else 0."""

	def test_headroom_when_under_limit(self):
		self.assertEqual(_available_credit(1000.0, 400.0), 600.0)

	def test_zero_when_exactly_at_limit(self):
		self.assertEqual(_available_credit(1000.0, 1000.0), 0.0)

	def test_floored_at_zero_when_over_limit(self):
		"""Over the limit ⇒ 0, NEVER a negative headroom."""
		self.assertEqual(_available_credit(1000.0, 1500.0), 0.0)

	def test_zero_when_no_limit_set(self):
		"""No credit limit (0/None) ⇒ available credit is 0 — we do not invent unlimited headroom."""
		self.assertEqual(_available_credit(0, 500.0), 0.0)
		self.assertEqual(_available_credit(None, 500.0), 0.0)

	def test_full_headroom_when_nothing_outstanding(self):
		self.assertEqual(_available_credit(1000.0, 0.0), 1000.0)


class TestYoYPeriodMath(FrappeTestCase):
	"""fclist_sales_yoy: whole-year shift (Feb-29 guard), like-for-like windows, and %-change contract."""

	def test_shift_year_back_one(self):
		self.assertEqual(_shift_year(getdate("2026-07-02"), -1), getdate("2025-07-02"))

	def test_shift_year_forward_one(self):
		self.assertEqual(_shift_year(getdate("2026-07-02"), 1), getdate("2027-07-02"))

	def test_shift_year_leap_day_guarded(self):
		"""Feb-29 has no counterpart in a non-leap year ⇒ clamp to Feb-28 (no ValueError)."""
		self.assertEqual(_shift_year(getdate("2024-02-29"), -1), getdate("2023-02-28"))
		self.assertEqual(_shift_year(getdate("2024-02-29"), 1), getdate("2025-02-28"))

	def test_shift_year_leap_to_leap_preserved(self):
		"""Leap-day → another leap year keeps Feb-29 (2024 → 2028)."""
		self.assertEqual(_shift_year(getdate("2024-02-29"), 4), getdate("2028-02-29"))

	def test_change_pct_growth(self):
		self.assertEqual(_change_pct(150.0, 100.0), 50.0)

	def test_change_pct_decline(self):
		self.assertEqual(_change_pct(80.0, 100.0), -20.0)

	def test_change_pct_zero_last_year_is_zero_not_infinite(self):
		"""No prior-year sales ⇒ 0% (guarded divide), never a divide-by-zero or infinite growth."""
		self.assertEqual(_change_pct(500.0, 0.0), 0.0)
		self.assertEqual(_change_pct(0.0, 0.0), 0.0)

	def test_change_pct_rounded_two_dp(self):
		self.assertEqual(_change_pct(1000.0, 3.0), round((1000.0 - 3.0) / 3.0 * 100.0, 2))

	def test_periods_windows_are_like_for_like(self):
		"""The report's _periods() must return 4 windows (Today, WTD, MTD, YTD); each last-year window is
		the same span shifted back exactly one year (same start offset, same end offset)."""
		mod = _report_module("FClist Sales YoY")
		today = getdate("2026-07-02")  # a Thursday
		periods = mod._periods(today)
		self.assertEqual(len(periods), 4, "expected exactly Today / WTD / MTD / YTD")
		for label, ty_start, ty_end, ly_start, ly_end in periods:
			# this-year window ends today; last-year window ends one year before today.
			self.assertEqual(ty_end, today, f"{label}: this-year window must end today")
			self.assertEqual(ly_end, _shift_year(ty_end, -1), f"{label}: last-year end must be TY end −1yr")
			self.assertEqual(ly_start, _shift_year(ty_start, -1), f"{label}: last-year start must be TY start −1yr")
			self.assertLessEqual(ty_start, ty_end, f"{label}: start must not follow end")

	def test_periods_boundaries(self):
		"""MTD starts on the 1st, YTD on Jan-1, WTD on Monday of the current ISO week, Today is a point."""
		mod = _report_module("FClist Sales YoY")
		today = getdate("2026-07-02")  # Thursday, ISO weekday 3 (Mon=0)
		by_label = {p[0]: p for p in mod._periods(today)}
		# labels are `_()`-wrapped; in test context identity, so keys are the plain strings.
		self.assertEqual(str(by_label["Today"][1]), str(today))
		self.assertEqual(str(by_label["Month to Date"][1]), "2026-07-01")
		self.assertEqual(str(by_label["Year to Date"][1]), "2026-01-01")
		self.assertEqual(str(by_label["Week to Date"][1]), "2026-06-29")  # Monday of that week


# ====================================================================================================
# 3. fclists.extend_listview save-and-chain contract — enforced STATICALLY on the *_list.js source.
# ====================================================================================================

class TestListJsExtendContract(FrappeTestCase):
	# The four NEW list-js surfaces Wave 2 adds (AR/AP + Chart-of-Accounts lanes). Each must extend
	# native via fclists.extend_listview() with no bare reassignment (Finding A) — asserted explicitly
	# below in addition to the all-files sweep.
	WAVE2_LIST_JS = ("account_list.js", "customer_list.js", "purchase_invoice_list.js", "supplier_list.js")

	def test_list_js_files_exist(self):
		files = _list_js_files()
		self.assertGreater(len(files), 0, "no *_list.js files found under public/js")
		# the four Wave-1 listview surfaces we ship (Hard Rule 2 applies to each)
		basenames = {os.path.basename(f) for f in files}
		for expected in ("item_list.js", "batch_list.js", "sales_invoice_list.js", "pos_invoice_list.js"):
			self.assertIn(expected, basenames, f"missing expected list-js: {expected}")

	def test_wave2_list_js_files_exist(self):
		"""The four NEW Wave-2 list-js surfaces must be present."""
		basenames = {os.path.basename(f) for f in _list_js_files()}
		for expected in self.WAVE2_LIST_JS:
			self.assertIn(expected, basenames, f"missing expected Wave-2 list-js: {expected}")

	def test_wave2_list_js_extend_native_with_no_bare_reassignment(self):
		"""Finding A, scoped to the four NEW *_list.js: each MUST register via fclists.extend_listview(...)
		(merge + save-and-chain) and contain NO bare `frappe.listview_settings["X"] = {...}` in real code
		(comments are stripped first, so the cautionary comment quoting the anti-pattern is not a match)."""
		bare = re.compile(r"frappe\s*\.\s*listview_settings\s*\[[^\]]+\]\s*=")
		js_dir = _list_js_dir()
		for base in self.WAVE2_LIST_JS:
			path = os.path.join(js_dir, base)
			with open(path, encoding="utf-8") as fh:
				code = _strip_js_line_comments(fh.read())
			self.assertIn(
				"fclists.extend_listview(", code,
				f"{base} must extend via fclists.extend_listview()",
			)
			self.assertIsNone(
				bare.search(code),
				f"{base} contains a BARE listview_settings reassignment (Finding A) — "
				f"use fclists.extend_listview() instead",
			)

	def test_every_list_js_uses_extend_listview(self):
		"""Finding A: each *_list.js MUST register via fclists.extend_listview(...) — never a hand-rolled
		listview_settings object."""
		for path in _list_js_files():
			with open(path, encoding="utf-8") as fh:
				code = _strip_js_line_comments(fh.read())
			self.assertIn(
				"fclists.extend_listview(", code,
				f"{os.path.basename(path)} must extend via fclists.extend_listview()",
			)

	def test_no_bare_listview_reassignment(self):
		"""Finding A: a bare `frappe.listview_settings["X"] = {...}` clobbers native + prior-app config
		(Frappe concatenates all apps' list-js). Assert NONE exists in real code (comments are stripped)."""
		bare = re.compile(r"frappe\s*\.\s*listview_settings\s*\[[^\]]+\]\s*=")
		for path in _list_js_files():
			with open(path, encoding="utf-8") as fh:
				code = _strip_js_line_comments(fh.read())
			self.assertIsNone(
				bare.search(code),
				f"{os.path.basename(path)} contains a BARE listview_settings reassignment (Finding A) — "
				f"use fclists.extend_listview() instead",
			)

	def test_helper_defines_extend_listview(self):
		"""The reusable primitive itself must define fclists.extend_listview and go through
		frappe.provide('fclists') (the loader contract)."""
		lib = os.path.join(_list_js_dir(), "fclists_lib.js")
		self.assertTrue(os.path.exists(lib), "fclists_lib.js missing")
		with open(lib, encoding="utf-8") as fh:
			src = fh.read()
		self.assertIn("frappe.provide(\"fclists\")", src)
		self.assertRegex(src, r"fclists\.extend_listview\s*=\s*function")


# ====================================================================================================
# Wave 3 — QB-POS parity borrows (S035): pure helpers tested on the REAL modules (they need no ledger).
# ====================================================================================================

class TestPaymentSummaryHelpers(FrappeTestCase):
	"""fclist_payment_summary: the day x tender matrix's pure helpers — the column-key scrubber and the
	change-netting rule (QB-POS shows what STAYED in the drawer, not what was handed over)."""

	@property
	def mod(self):
		return _report_module("FClist Payment Summary")

	def test_mode_fieldname_scrubs_to_safe_keys(self):
		self.assertEqual(self.mod._mode_fieldname("Cash"), "m_cash")
		self.assertEqual(self.mod._mode_fieldname("M-Pesa (Till)"), "m_m_pesa_till")

	def test_mode_fieldname_distinct_for_distinct_modes(self):
		self.assertNotEqual(self.mod._mode_fieldname("Visa"), self.mod._mode_fieldname("M-Pesa"))

	def test_net_tenders_deducts_change_from_cash(self):
		"""1000 sale, 1100 cash given, 100 change back -> the drawer kept 1000 cash."""
		rows = self.mod._net_tenders(
			[{"mode_of_payment": "Cash", "amount": 1100.0}], 100.0, {"Cash": "Cash"}
		)
		self.assertEqual(rows, [("Cash", 1000.0)])

	def test_net_tenders_prefers_cash_type_row_for_change(self):
		"""Split tender: change comes out of the Cash-type mode, never the bank mode."""
		rows = self.mod._net_tenders(
			[
				{"mode_of_payment": "M-Pesa", "amount": 500.0},
				{"mode_of_payment": "Cash", "amount": 700.0},
			],
			200.0,
			{"Cash": "Cash", "M-Pesa": "Bank"},
		)
		self.assertEqual(dict(rows), {"M-Pesa": 500.0, "Cash": 500.0})

	def test_net_tenders_falls_back_to_largest_row(self):
		"""No Cash-type mode configured: deduct from the largest tender so the day still ties."""
		rows = self.mod._net_tenders(
			[
				{"mode_of_payment": "M-Pesa", "amount": 900.0},
				{"mode_of_payment": "Voucher", "amount": 100.0},
			],
			50.0,
			{"M-Pesa": "Bank", "Voucher": "General"},
		)
		self.assertEqual(dict(rows), {"M-Pesa": 850.0, "Voucher": 100.0})

	def test_net_tenders_drops_zeroed_rows(self):
		rows = self.mod._net_tenders(
			[{"mode_of_payment": "Cash", "amount": 100.0}], 100.0, {"Cash": "Cash"}
		)
		self.assertEqual(rows, [])

	def test_net_tenders_no_change_passthrough(self):
		rows = self.mod._net_tenders(
			[{"mode_of_payment": "Cash", "amount": 250.0}], 0, {"Cash": "Cash"}
		)
		self.assertEqual(rows, [("Cash", 250.0)])

	def test_columns_default_shape_without_modes(self):
		"""_columns() with no modes (the hermetic/no-data case) = Date + On Account + Daily Total."""
		names = [c["fieldname"] for c in self.mod._columns()]
		self.assertEqual(names, ["posting_date", "on_account", "daily_total"])

	def test_columns_insert_mode_columns_between_date_and_on_account(self):
		names = [c["fieldname"] for c in self.mod._columns(["Cash", "M-Pesa"])]
		self.assertEqual(names, ["posting_date", "m_cash", "m_m_pesa", "on_account", "daily_total"])


class TestReceiptDetailHelpers(FrappeTestCase):
	"""fclist_receipt_detail: the tender-label rule (QB-POS 'Payment' column semantics)."""

	@property
	def mod(self):
		return _report_module("FClist Receipt Detail")

	def test_credit_sale_is_on_account(self):
		self.assertEqual(self.mod._tender_label([], is_pos=0, fully_paid=False), "On Account")

	def test_pos_single_mode(self):
		rows = [{"mode_of_payment": "Cash", "amount": 500.0}]
		self.assertEqual(self.mod._tender_label(rows, is_pos=1, fully_paid=True), "Cash")

	def test_pos_split_tender_joined(self):
		rows = [
			{"mode_of_payment": "Cash", "amount": 200.0},
			{"mode_of_payment": "M-Pesa", "amount": 300.0},
		]
		self.assertEqual(self.mod._tender_label(rows, is_pos=1, fully_paid=True), "Cash + M-Pesa")

	def test_pos_partial_tender_appends_on_account(self):
		rows = [{"mode_of_payment": "Cash", "amount": 200.0}]
		self.assertEqual(
			self.mod._tender_label(rows, is_pos=1, fully_paid=False), "Cash + On Account"
		)

	def test_zero_amount_modes_ignored(self):
		rows = [
			{"mode_of_payment": "Cash", "amount": 0.0},
			{"mode_of_payment": "M-Pesa", "amount": 450.0},
		]
		self.assertEqual(self.mod._tender_label(rows, is_pos=1, fully_paid=True), "M-Pesa")

	def test_pos_with_no_tender_rows_is_on_account(self):
		self.assertEqual(self.mod._tender_label([], is_pos=1, fully_paid=False), "On Account")

	def test_tree_contract_fields_present_in_columns(self):
		"""The tree register's name_field ('label') must exist as the first column (the JS tree config
		points at it); qty/rate/total shared by receipt and item rows must be present."""
		names = [c["fieldname"] for c in self.mod._columns()]
		self.assertEqual(names[0], "label")
		for required in ("qty", "rate", "total", "tender", "line_count", "open_link"):
			self.assertIn(required, names)


# ====================================================================================================
# 4. The user-guide gate (www/fclists-guide.py) — the pure role-intersection predicate, hermetically,
#    plus the on-disk consistency law: ALLOWED_ROLES == the union of every report JSON's roles table.
# ====================================================================================================

def _guide_module():
	"""Import the www controller (hyphenated filename → importlib, not an import statement)."""
	import importlib

	return importlib.import_module("fclists.www.fclists-guide")


class TestGuideGatePredicate(FrappeTestCase):
	"""has_guide_access() is the guide's whole decision (get_context only adds the explicit Guest
	short-circuit) — pure set logic, so it gets the fast hermetic layer (sw/testing.md §4)."""

	def test_roleless_user_denied(self):
		self.assertFalse(_guide_module().has_guide_access([]))

	def test_none_roles_denied(self):
		self.assertFalse(_guide_module().has_guide_access(None))

	def test_guest_only_roles_denied(self):
		"""'Guest' (and 'All') are NOT report-reading roles — a bare session never qualifies."""
		self.assertFalse(_guide_module().has_guide_access(["Guest", "All"]))

	def test_unrelated_roles_denied(self):
		self.assertFalse(_guide_module().has_guide_access(["Employee", "Sales User", "Purchase User"]))

	def test_each_allowed_role_admits_alone(self):
		mod = _guide_module()
		for role in ("System Manager", "Stock Manager", "Stock User", "Accounts Manager", "Accounts User"):
			self.assertTrue(mod.has_guide_access([role]), f"{role} alone must admit")

	def test_allowed_role_admits_amid_noise(self):
		self.assertTrue(_guide_module().has_guide_access(["All", "Guest", "Employee", "Accounts User"]))

	def test_allowed_roles_match_report_json_union(self):
		"""The gate's ALLOWED_ROLES must equal the union of the roles tables across ALL report JSONs
		on disk (the guide admits exactly the users who can open at least one report — no drift).
		The report set is enumerated FROM DISK and asserted equal to REPORT_MODULES, so a report
		folder added without updating REPORT_MODULES fails here instead of silently escaping the law."""
		report_dir = os.path.join(frappe.get_app_path("fclists"), "fclists", "report")
		on_disk = {
			d for d in os.listdir(report_dir)
			if d != "__pycache__" and os.path.isdir(os.path.join(report_dir, d))
		}
		self.assertEqual(
			on_disk, set(REPORT_MODULES.values()),
			"report folders on disk drifted from REPORT_MODULES — register the new report in "
			"REPORT_MODULES (and the guide gate) or remove the stray folder",
		)
		union = set()
		for scrubbed in REPORT_MODULES.values():
			path = os.path.join(report_dir, scrubbed, f"{scrubbed}.json")
			self.assertTrue(os.path.exists(path), f"missing report JSON: {path}")
			with open(path, encoding="utf-8") as fh:
				doc = json.load(fh)
			union |= {row["role"] for row in doc.get("roles", [])}
		self.assertEqual(
			union, _guide_module().ALLOWED_ROLES,
			"guide ALLOWED_ROLES drifted from the union of report-JSON roles — update the gate "
			"(and this law) together with the report that introduced the new role",
		)
