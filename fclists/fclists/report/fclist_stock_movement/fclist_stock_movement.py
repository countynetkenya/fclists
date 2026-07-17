"""FClist Stock Movement — recent stock ledger moves, split into in/out columns.

Per Stock Ledger Entry: posting_date, item, warehouse, voucher_type, voucher_no, in_qty (actual_qty when
positive), out_qty (abs actual_qty when negative), valuation_rate. A denser, split-column reading of the
native Stock Ledger — the raw SLE list crams the signed qty into one column.

Security (Finding B): role-gated on the Report doc. The row query runs through frappe.get_list → read
permission is checked and User Permissions scope the rows.
v16-safe: explicit order_by (posting_date desc, then posting_time/creation desc for intra-day order);
no raw SQL. Sector-neutral; gated by site_config fclists_enabled.

Companies (2026-07-17 tree-checkbox yokoten — see fclists.nav_options, thin copy of
fcbi/fcbi/consolidate.py's pattern): `companies` MultiSelectList wins over the legacy single `company`
Link. No Cost Centre filter this wave — a stock ledger move is not cost-centre attributed the way a
ledger/invoice row is; out of scope per the yokoten applicability table.
"""
import frappe
from frappe import _
from frappe.utils import flt, cint, add_days, nowdate

from fclists.nav_options import resolve_companies_filter


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not _enabled():
		return _columns(), []
	return _columns(), _data(filters)


def _enabled():
	val = frappe.conf.get("fclists_enabled")
	return True if val is None else cint(val)


def _columns():
	return [
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 160},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 150},
		{"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 140},
		{"label": _("Voucher No"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 170},
		{"label": _("In Qty"), "fieldname": "in_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Out Qty"), "fieldname": "out_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Valuation Rate"), "fieldname": "valuation_rate", "fieldtype": "Currency", "width": 120},
	]


def _data(filters):
	days = cint(filters.get("window_days")) or 30
	from_date = filters.get("from_date") or add_days(nowdate(), -days)
	to_date = filters.get("to_date") or nowdate()

	sle_filters = {
		"is_cancelled": 0,
		"posting_date": ["between", [from_date, to_date]],
	}
	companies = resolve_companies_filter(filters.get("companies"), filters.get("company"))
	if companies:
		sle_filters["company"] = ["in", companies]
	if filters.get("item"):
		sle_filters["item_code"] = filters.item
	if filters.get("warehouse"):
		sle_filters["warehouse"] = filters.warehouse
	# QB-POS parity (S059): split the one movement list by transaction type so a Quantity Adjustment
	# history (voucher_type = Stock Reconciliation) and a Transfer history (Stock Entry of a given
	# stock_entry_type) each read the SAME native ledger through their own lens — no shadow list.
	if filters.get("voucher_type"):
		sle_filters["voucher_type"] = filters.voucher_type
	if filters.get("stock_entry_type"):
		# stock_entry_type lives on Stock Entry, not the SLE, so resolve the voucher_nos in-window and
		# scope the ledger to them (implies voucher_type = Stock Entry). Empty set → no rows, honestly.
		se_names = frappe.get_all(
			"Stock Entry",
			filters={
				"stock_entry_type": filters.stock_entry_type,
				"docstatus": 1,
				"posting_date": ["between", [from_date, to_date]],
			},
			pluck="name",
			order_by="posting_date desc",
		)
		sle_filters["voucher_type"] = "Stock Entry"
		sle_filters["voucher_no"] = ["in", se_names or [""]]

	# permission-checked (get_list): role read-perm + User Permissions scope the rows.
	entries = frappe.get_list(
		"Stock Ledger Entry",
		filters=sle_filters,
		fields=[
			"posting_date", "item_code", "warehouse", "voucher_type",
			"voucher_no", "actual_qty", "valuation_rate",
		],
		order_by="posting_date desc, posting_time desc, creation desc",
		limit=cint(filters.get("limit")) or 500,
	)

	rows = []
	for e in entries:
		aq = flt(e.actual_qty)
		rows.append({
			"posting_date": e.posting_date,
			"item_code": e.item_code,
			"warehouse": e.warehouse,
			"voucher_type": e.voucher_type,
			"voucher_no": e.voucher_no,
			"in_qty": aq if aq > 0 else 0.0,
			"out_qty": -aq if aq < 0 else 0.0,
			"valuation_rate": flt(e.valuation_rate),
		})
	return rows
