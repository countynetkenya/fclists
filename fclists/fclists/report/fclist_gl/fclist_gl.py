"""FClist GL — dense recent-ledger board (QBO "Journal / General Ledger" density parity).

A fast, filterable window onto native GL Entry rows: posting date, account, debit, credit, voucher
type/no, party and remarks. The native GL Entry list is admin-oriented and unsorted for daily review; this
Script Report gives the QuickBooks-style ledger scroll (newest first) with the columns an accountant scans.

Security (Finding B): role-gated on its Report doc (native Accounts roles + System Manager) — never
world-readable. The row query runs through frappe.get_list → read permission is checked and User
Permissions scope the rows (a user permitted to Company A never sees Company B's ledger). No raw SQL,
so no build_match_conditions needed.

Companies / Cost Centre (2026-07-17 tree-checkbox yokoten from fcbi/fcbi/consolidate.py, D-048 clean-room
thin copy — see fclists.nav_options for the provider): the `companies` MultiSelectList (tree, is_group
expands to descendants) WINS when set; the legacy single `company` Link keeps working as the fallback
(fclists.nav_options.resolve_companies_filter). `cost_center` is a MultiSelectList straight onto GL
Entry.cost_center (the ledger row's own dimension — no expansion-then-join needed, GL Entry IS the leaf
table) via fclists.nav_options.resolve_cost_centre_filter.

v16-safe: explicit order_by (posting_date desc, creation desc); no grouped-sum field strings. A bounded
row limit keeps the ledger scroll responsive. Sector-neutral (no client literal).
"""
import frappe
from frappe import _
from frappe.utils import cint

from fclists.nav_options import resolve_companies_filter, resolve_cost_centre_filter


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 240},
		{"label": _("Debit"), "fieldname": "debit", "fieldtype": "Currency", "width": 120},
		{"label": _("Credit"), "fieldname": "credit", "fieldtype": "Currency", "width": 120},
		{"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 140},
		{"label": _("Voucher No"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 170},
		{"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data", "width": 110},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 180},
		{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 260},
	]


def _data(filters):
	gle_filters = {"is_cancelled": 0}
	companies = resolve_companies_filter(filters.get("companies"), filters.get("company"))
	if companies:
		gle_filters["company"] = ["in", companies]
	cost_centers = resolve_cost_centre_filter(filters.get("cost_center"))
	if cost_centers:
		gle_filters["cost_center"] = ["in", cost_centers]
	if filters.get("account"):
		gle_filters["account"] = filters.account
	if filters.get("party"):
		gle_filters["party"] = filters.party
	if filters.get("from_date") and filters.get("to_date"):
		gle_filters["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		gle_filters["posting_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		gle_filters["posting_date"] = ["<=", filters.to_date]

	limit = cint(filters.get("limit")) or 500

	# permission-checked (get_list): role read-perm + User Permissions scope the ledger rows.
	return frappe.get_list(
		"GL Entry",
		filters=gle_filters,
		fields=[
			"posting_date", "account", "debit", "credit",
			"voucher_type", "voucher_no", "party_type", "party", "remarks",
		],
		order_by="posting_date desc, creation desc",
		limit=limit,
	)
