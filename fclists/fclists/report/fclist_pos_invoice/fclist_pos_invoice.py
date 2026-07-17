"""FClist POS Invoice — POS receipts board (QBO-POS density parity).

Every POS Invoice with its tender split: date, customer, grand total, paid amount, the mode-of-payment
summary (e.g. "Cash: 500, M-Pesa: 1200"), and an is_return flag. The mode-of-payment split lives in the
child table `Sales Invoice Payment` (parent = POS Invoice), so a plain list view cannot show it — this
Script Report is the native tool.

Security (Finding B): role-gated on its Report doc (native Accounts roles + System Manager). The
row-driving POS Invoice query runs through frappe.get_list → read permission is checked and User
Permissions scope the rows; tender child rows are read only for those already-permitted receipts.
No raw SQL, so no build_match_conditions needed.
v16-safe: explicit order_by; per-invoice tender totals summed in PYTHON (frappe get_all rejects
"sum(x) as y" field strings); read-only.

Companies / Cost Centre (2026-07-17 tree-checkbox yokoten — see fclists.nav_options, thin copy of
fcbi/fcbi/consolidate.py's pattern): `companies` MultiSelectList wins over the legacy single `company`
Link; `cost_center` filters POS Invoice's own header cost_center field.
"""
import frappe
from frappe import _
from frappe.utils import flt

from fclists.nav_options import resolve_companies_filter, resolve_cost_centre_filter


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Receipt"), "fieldname": "name", "fieldtype": "Link", "options": "POS Invoice", "width": 160},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 180},
		{"label": _("POS Profile"), "fieldname": "pos_profile", "fieldtype": "Link", "options": "POS Profile", "width": 140},
		{"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Paid"), "fieldname": "paid_amount", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("Tender Split"), "fieldname": "mode_of_payment", "fieldtype": "Data", "width": 240},
		{"label": _("Return"), "fieldname": "is_return_flag", "fieldtype": "Data", "width": 90},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 90},
	]


def _data(filters):
	pos_filters = {"docstatus": 1}
	companies = resolve_companies_filter(filters.get("companies"), filters.get("company"))
	if companies:
		pos_filters["company"] = ["in", companies]
	cost_centers = resolve_cost_centre_filter(filters.get("cost_center"))
	if cost_centers:
		pos_filters["cost_center"] = ["in", cost_centers]
	if filters.get("pos_profile"):
		pos_filters["pos_profile"] = filters.pos_profile
	if filters.get("from_date") and filters.get("to_date"):
		pos_filters["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		pos_filters["posting_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		pos_filters["posting_date"] = ["<=", filters.to_date]

	# permission-checked (get_list): role read-perm + User Permissions scope the receipt rows.
	invoices = frappe.get_list(
		"POS Invoice",
		filters=pos_filters,
		fields=[
			"name", "posting_date", "customer", "pos_profile",
			"grand_total", "paid_amount", "is_return", "currency",
		],
		order_by="posting_date desc, name desc",
	)
	if not invoices:
		return []

	names = [i.name for i in invoices]

	# Tender lines for these receipts (child table Sales Invoice Payment). Sum per-parent in Python.
	# get_all here is safe: child rows scoped to parents from the permission-checked get_list above.
	payments = frappe.get_all(
		"Sales Invoice Payment",
		filters={"parenttype": "POS Invoice", "parent": ["in", names]},
		fields=["parent", "mode_of_payment", "amount"],
		order_by="parent asc, idx asc",
	)
	tender = {}
	for p in payments:
		bucket = tender.setdefault(p.parent, {})
		mop = p.mode_of_payment or _("Unspecified")
		bucket[mop] = flt(bucket.get(mop, 0.0)) + flt(p.amount)

	rows = []
	for inv in invoices:
		split = tender.get(inv.name, {})
		summary = ", ".join("{0}: {1}".format(mop, flt(amt)) for mop, amt in split.items())
		rows.append({
			"name": inv.name,
			"posting_date": inv.posting_date,
			"customer": inv.customer,
			"pos_profile": inv.pos_profile,
			"grand_total": flt(inv.grand_total),
			"paid_amount": flt(inv.paid_amount),
			"mode_of_payment": summary,
			"is_return_flag": _("Return") if inv.is_return else "",
			"currency": inv.currency,
		})
	return rows
