# Copyright (c) 2026, Flowcore and Contributors
# See license.txt
"""Hermetic unit tests for FCLists — pure logic only, NO live ledger required.

These tests cover the three ledger-free surfaces of the app:

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

  3. The `fclists.extend_listview` SAVE-AND-CHAIN contract enforced at the source level: a JS-logic unit is
     impractical in Python, so instead we STATICALLY assert every `public/js/*_list.js` file goes through
     `fclists.extend_listview(...)` and contains NO bare `frappe.listview_settings["X"] = {...}`
     reassignment (Finding A — a bare `=` drops native + prior-app list config because Frappe concatenates
     all apps' list-js into one bundle).

Runnable via:  bench --site <site> run-tests --app fclists --module \
                 fclists.fclists.tests.test_fclists
"""

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
	"FClist Item Stock": "fclist_item_stock",
	"FClist Batch Expiry": "fclist_batch_expiry",
	"FClist Reorder": "fclist_reorder",
	"FClist Sales Invoice": "fclist_sales_invoice",
	"FClist Sales History": "fclist_sales_history",
	"FClist Returns": "fclist_returns",
	"FClist Payments": "fclist_payments",
	"FClist POS Invoice": "fclist_pos_invoice",
	"FClist Stock Movement": "fclist_stock_movement",
}

# Reports that carry the site_config `_enabled()` capability gate (the stock/inventory ones).
REPORTS_WITH_ENABLE_GATE = {
	"FClist Item Stock",
	"FClist Batch Expiry",
	"FClist Reorder",
	"FClist Stock Movement",
}

# The doctypes any FCLists report column may legally reference (Link/Dynamic Link options).
# ALL native to Frappe/ERPNext — never a flowcore/fcduka/settle/etc. doctype (Hard Rule 1).
ALLOWED_NATIVE_OPTION_DOCTYPES = {
	"Item", "Item Group", "UOM", "Batch", "Warehouse", "Customer", "Supplier",
	"Sales Invoice", "POS Invoice", "Payment Entry", "Mode of Payment", "POS Profile",
	"Currency", "User", "Account", "Stock Ledger Entry", "GL Entry", "Bin",
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
# 3. fclists.extend_listview save-and-chain contract — enforced STATICALLY on the *_list.js source.
# ====================================================================================================

class TestListJsExtendContract(FrappeTestCase):
	def test_list_js_files_exist(self):
		files = _list_js_files()
		self.assertGreater(len(files), 0, "no *_list.js files found under public/js")
		# the four listview surfaces we ship (Hard Rule 2 applies to each)
		basenames = {os.path.basename(f) for f in files}
		for expected in ("item_list.js", "batch_list.js", "sales_invoice_list.js", "pos_invoice_list.js"):
			self.assertIn(expected, basenames, f"missing expected list-js: {expected}")

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
