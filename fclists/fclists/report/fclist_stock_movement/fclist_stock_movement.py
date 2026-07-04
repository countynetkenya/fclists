"""FClist Stock Movement — recent stock ledger moves, split into in/out columns.

Per Stock Ledger Entry: posting_date, item, warehouse, voucher_type, voucher_no, in_qty (actual_qty when
positive), out_qty (abs actual_qty when negative), valuation_rate. A denser, split-column reading of the
native Stock Ledger — the raw SLE list crams the signed qty into one column.

Security (Finding B): role-gated on the Report doc. The row query runs through frappe.get_list → read
permission is checked and User Permissions scope the rows.
v16-safe: explicit order_by (posting_date desc, then posting_time/creation desc for intra-day order);
no raw SQL. Sector-neutral; gated by site_config fclists_enabled.
"""
import frappe
from frappe import _
from frappe.utils import flt, cint, add_days, nowdate


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
	if filters.get("company"):
		sle_filters["company"] = filters.company
	if filters.get("item"):
		sle_filters["item_code"] = filters.item
	if filters.get("warehouse"):
		sle_filters["warehouse"] = filters.warehouse

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
