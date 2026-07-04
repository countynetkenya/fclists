"""FClist Sales by Department — sales grouped by item_group (the "department").

Per item_group over a date range: qty, revenue, share% of total revenue. item_group is the Sales Invoice
Item's own group (the department the line belongs to). The native list has no "group by department with sum
+ share" view, so this Script Report is the native tool.

Security (Finding B): role-gated on the Report doc (native Accounts roles + System Manager) — never
world-readable. The row-driving Sales Invoice query runs through frappe.get_list → read permission is
checked and User Permissions scope the rows; line rows are read only for those already-permitted
invoices. No raw SQL, so no build_match_conditions needed.
v16-safe: sums grouped in PYTHON (frappe.get_all rejects "sum(x) as y" field strings); every query passes
an explicit order_by. Sector-neutral (no client literal — "department" == item_group, config-driven).
"""
import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Department"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 220},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 120},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 150},
		{"label": _("Share %"), "fieldname": "share_pct", "fieldtype": "Percent", "width": 110},
	]


def _data(filters):
	si_filters = {"docstatus": 1, "is_return": 0}
	if filters.get("company"):
		si_filters["company"] = filters.company
	if filters.get("from_date") and filters.get("to_date"):
		si_filters["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		si_filters["posting_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		si_filters["posting_date"] = ["<=", filters.to_date]

	# permission-checked (get_list): role read-perm + User Permissions scope the invoice set.
	invoices = frappe.get_list(
		"Sales Invoice", filters=si_filters, fields=["name"], order_by="posting_date desc"
	)
	if not invoices:
		return []
	inv_names = [i.name for i in invoices]

	# group by item_group in PYTHON (no "sum(x) as y" field strings).
	# get_all here is safe: child rows scoped to parents from the permission-checked get_list above.
	qty = {}
	revenue = {}
	for li in frappe.get_all(
		"Sales Invoice Item",
		filters={"parent": ["in", inv_names]},
		fields=["item_group", "stock_qty", "qty", "base_net_amount", "amount"],
		order_by="parent asc",
	):
		grp = li.item_group or _("(Unassigned)")
		qty[grp] = flt(qty.get(grp, 0)) + (flt(li.stock_qty) or flt(li.qty))
		revenue[grp] = flt(revenue.get(grp, 0)) + (flt(li.base_net_amount) or flt(li.amount))

	if not revenue:
		return []

	total_revenue = flt(sum(revenue.values()))

	# order by revenue desc, tie-break department asc
	ordered = sorted(revenue.keys(), key=lambda g: (-flt(revenue.get(g, 0)), g))

	rows = []
	for grp in ordered:
		rev = flt(revenue.get(grp, 0))
		rows.append({
			"item_group": grp,
			"qty": flt(qty.get(grp, 0)),
			"revenue": rev,
			"share_pct": flt(rev / total_revenue * 100.0, 2) if total_revenue else 0.0,
		})
	return rows
