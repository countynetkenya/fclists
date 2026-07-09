"""FClist Receiving — the line-level goods-received register (QB-POS "Received Items" parity).

One row per submitted Purchase Receipt LINE: posting date, the receipt (link), supplier, company, item,
quantity received, the received rate (the supplier-invoice COST that becomes the valuation basis), the
line amount, and the store it landed in. The native Purchase Receipt list is header-only; this Script
Report is the item-level "what came in, from whom, at what cost, into which store" board a manager reads
without opening each receipt one by one.

Security (Finding B): role-gated on its Report doc (Stock User / Accounts Manager / System Manager) —
never world-readable. The row-driving Purchase Receipt query runs through frappe.get_list → read
permission is checked and User Permissions scope the rows (a user permitted to Company A never sees
Company B's receipts); the item child rows are read ONLY for those already-permitted receipts (scoped by
``parent in <permitted names>``). No raw SQL, so no build_match_conditions needed.

v16-safe: explicit order_by on every read; a window_days default so an unfiltered open is bounded;
read-only. Sector-neutral; gated by site_config ``fclists_enabled``. Purchase Receipt is a NATIVE erpnext
doctype, so this report lives in clean-room fclists (erpnext-only dep, no fcduka import).
"""
import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, nowdate


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
		{"label": _("Receipt"), "fieldname": "purchase_receipt", "fieldtype": "Link", "options": "Purchase Receipt", "width": 170},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 200},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 160},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 180},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 90},
		{"label": _("Rate (Cost)"), "fieldname": "rate", "fieldtype": "Currency", "width": 110},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 160},
	]


def _data(filters):
	days = cint(filters.get("window_days")) or 30
	from_date = filters.get("from_date") or add_days(nowdate(), -days)
	to_date = filters.get("to_date") or nowdate()

	pr_filters = {
		"docstatus": 1,
		"posting_date": ["between", [from_date, to_date]],
	}
	if filters.get("company"):
		pr_filters["company"] = filters.company
	if filters.get("supplier"):
		pr_filters["supplier"] = filters.supplier

	# permission-checked (get_list): role read-perm + User Permissions scope the receipt rows.
	receipts = frappe.get_list(
		"Purchase Receipt",
		filters=pr_filters,
		fields=["name", "posting_date", "supplier", "company"],
		order_by="posting_date desc, name desc",
	)
	if not receipts:
		return []
	header = {r.name: r for r in receipts}

	# get_all below is safe: child rows are scoped to the parents from the permission-checked get_list
	# above (a user who cannot read the receipt never reaches its lines). Explicit order_by (v16).
	item_filters = {"parenttype": "Purchase Receipt", "parent": ["in", list(header)], "docstatus": 1}
	if filters.get("item"):
		item_filters["item_code"] = filters.item
	lines = frappe.get_all(
		"Purchase Receipt Item",
		filters=item_filters,
		fields=["parent", "item_code", "qty", "rate", "amount", "warehouse"],
		order_by="parent asc, idx asc",
		parent_doctype="Purchase Receipt",
	)

	rows = []
	for ln in lines:
		h = header.get(ln.parent)
		if not h:
			continue
		rows.append({
			"posting_date": h.posting_date,
			"purchase_receipt": ln.parent,
			"supplier": h.supplier,
			"company": h.company,
			"item_code": ln.item_code,
			"qty": flt(ln.qty),
			"rate": flt(ln.rate),
			"amount": flt(ln.amount),
			"warehouse": ln.warehouse,
		})
	return rows
