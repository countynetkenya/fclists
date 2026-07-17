"""FClist Receipt Detail — the expandable per-receipt register (QB-POS "Sales Receipt Detail" parity).

One collapsible row per submitted sales receipt (Sales Invoice, POS included) — receipt no, date, time,
Sales/Return type, customer, total qty sold, total, how it was tendered, the cashier who rang it and the
line count — expanding (native query-report tree) to the receipt's item lines: item, qty, rate, amount.
This is the QB-POS screen a manager scrolls to answer "what exactly went out on receipt 168737?" without
opening each invoice.

Delta over the siblings: FClist Sales History is the flat header register (open/print); FClist POS Invoice
covers the native POS Invoice doctype. This report adds the LINE-ITEM drill-down and the per-receipt qty /
tender / line-count density of the QB-POS detail screen, over Sales Invoice.

Security (Finding B): role-gated on its Report doc (native Accounts roles + System Manager). The
row-driving Sales Invoice query runs through frappe.get_list → read permission is checked and User
Permissions scope the rows; item/tender child rows are read only for those already-permitted receipts.
No raw SQL, so no build_match_conditions needed.
v16-safe: explicit order_by; read-only; no grouped-sum field strings.

Companies / Cost Centre (2026-07-17 tree-checkbox yokoten — see fclists.nav_options, thin copy of
fcbi/fcbi/consolidate.py's pattern): `companies` MultiSelectList wins over the legacy single `company`
Link; `cost_center` filters Sales Invoice's own header cost_center field.
"""
import frappe
from frappe import _
from frappe.utils import flt

from fclists.nav_options import resolve_companies_filter, resolve_cost_centre_filter


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _tender_label(payment_rows, is_pos, fully_paid):
	"""Human tender summary for a receipt (pure): nonzero modes joined " + ", credit sales "On Account",
	a partially tendered POS sale "<modes> + On Account". No rows and no POS flag -> "On Account"."""
	modes = []
	for p in payment_rows or []:
		if flt(p.get("amount")) and p.get("mode_of_payment") and p["mode_of_payment"] not in modes:
			modes.append(p["mode_of_payment"])
	if not is_pos or not modes:
		return "On Account"
	label = " + ".join(modes)
	return label if fully_paid else label + " + On Account"


def _columns():
	return [
		{"label": _("Receipt / Item"), "fieldname": "label", "fieldtype": "Data", "width": 240},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Time"), "fieldname": "posting_time", "fieldtype": "Time", "width": 90},
		{"label": _("Type"), "fieldname": "receipt_type", "fieldtype": "Data", "width": 80},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 180},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 80},
		{"label": _("Rate"), "fieldname": "rate", "fieldtype": "Currency", "options": "currency", "width": 100},
		{"label": _("Total"), "fieldname": "total", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Tender"), "fieldname": "tender", "fieldtype": "Data", "width": 140},
		{"label": _("Cashier"), "fieldname": "owner", "fieldtype": "Link", "options": "User", "width": 170},
		{"label": _("Lines"), "fieldname": "line_count", "fieldtype": "Int", "width": 70},
		{"label": _("Open / Print"), "fieldname": "open_link", "fieldtype": "Link", "options": "Sales Invoice", "width": 150},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 90},
	]


def _data(filters):
	si_filters = {"docstatus": 1}
	companies = resolve_companies_filter(filters.get("companies"), filters.get("company"))
	if companies:
		si_filters["company"] = ["in", companies]
	cost_centers = resolve_cost_centre_filter(filters.get("cost_center"))
	if cost_centers:
		si_filters["cost_center"] = ["in", cost_centers]
	if filters.get("customer"):
		si_filters["customer"] = filters.customer
	if filters.get("owner"):
		si_filters["owner"] = filters.owner
	if filters.get("only_pos"):
		si_filters["is_pos"] = 1
	if filters.get("from_date") and filters.get("to_date"):
		si_filters["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		si_filters["posting_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		si_filters["posting_date"] = ["<=", filters.to_date]

	# permission-checked (get_list): role read-perm + User Permissions scope the receipt rows.
	invoices = frappe.get_list(
		"Sales Invoice",
		filters=si_filters,
		fields=[
			"name", "posting_date", "posting_time", "customer", "total_qty", "grand_total",
			"outstanding_amount", "is_pos", "is_return", "owner", "currency",
		],
		order_by="posting_date desc, posting_time desc, name desc",
	)
	names = [si.name for si in invoices]

	# get_all below is safe: child rows scoped to parents from the permission-checked get_list above.
	items_by_parent = {}
	payments_by_parent = {}
	if names:
		show_items = filters.get("show_items", 1)
		if int(show_items or 0):
			for it in frappe.get_all(
				"Sales Invoice Item",
				filters={"parenttype": "Sales Invoice", "parent": ["in", names], "docstatus": 1},
				fields=["parent", "item_code", "item_name", "qty", "rate", "amount"],
				order_by="parent asc, idx asc",
				parent_doctype="Sales Invoice",
			):
				items_by_parent.setdefault(it.parent, []).append(it)
		pos_names = [si.name for si in invoices if si.is_pos]
		if pos_names:
			for p in frappe.get_all(
				"Sales Invoice Payment",
				filters={"parenttype": "Sales Invoice", "parent": ["in", pos_names], "docstatus": 1},
				fields=["parent", "mode_of_payment", "amount"],
				order_by="parent asc, idx asc",
				parent_doctype="Sales Invoice",
			):
				payments_by_parent.setdefault(p.parent, []).append(p)

	rows = []
	for si in invoices:
		lines = items_by_parent.get(si.name, [])
		rows.append({
			"label": si.name,
			"parent_label": "",
			"indent": 0,
			"posting_date": si.posting_date,
			"posting_time": si.posting_time,
			"receipt_type": _("Return") if si.is_return else _("Sales"),
			"customer": si.customer,
			"qty": flt(si.total_qty),
			"total": flt(si.grand_total),
			"tender": _tender_label(
				payments_by_parent.get(si.name), si.is_pos, flt(si.outstanding_amount) <= 0
			),
			"owner": si.owner,
			"line_count": len(lines),
			"open_link": si.name,
			"currency": si.currency,
		})
		for it in lines:
			rows.append({
				"label": f"{it.item_code} — {it.item_name}" if it.item_name and it.item_name != it.item_code else it.item_code,
				"parent_label": si.name,
				"indent": 1,
				"qty": flt(it.qty),
				"rate": flt(it.rate),
				"total": flt(it.amount),
				"currency": si.currency,
			})
	return rows
