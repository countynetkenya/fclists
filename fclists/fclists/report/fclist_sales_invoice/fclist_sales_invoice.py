"""FClist Sales Invoice — dense AR sales board (QBO-POS density parity).

A single glance at every sales invoice: date, customer, total, what is still outstanding, its status, and
a computed OVERDUE flag (due_date < today AND outstanding_amount > 0). The native Sales Invoice list cannot
show an "overdue" column because it is derived from two fields against today's date — this Script Report is
the native tool.

Security (Finding B): role-gated on its Report doc (native Accounts roles + System Manager) — never
world-readable. The row query runs through frappe.get_list → read permission is checked and User
Permissions scope the rows (a user permitted to Company A never sees Company B's invoices). No raw
SQL, so no build_match_conditions needed.
v16-safe: explicit order_by; no grouped-sum field strings (the total row is summed in Python).

Companies / Cost Centre (2026-07-17 tree-checkbox yokoten — see fclists.nav_options, thin copy of
fcbi/fcbi/consolidate.py's pattern): `companies` MultiSelectList wins over the legacy single `company`
Link; `cost_center` filters Sales Invoice's own header cost_center field.
"""
import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from fclists.nav_options import resolve_companies_filter, resolve_cost_centre_filter


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Invoice"), "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice", "width": 160},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 200},
		{"label": _("Due Date"), "fieldname": "due_date", "fieldtype": "Date", "width": 100},
		{"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Outstanding"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Overdue"), "fieldname": "overdue", "fieldtype": "Data", "width": 90},
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
	if filters.get("status"):
		si_filters["status"] = filters.status
	if filters.get("from_date") and filters.get("to_date"):
		si_filters["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		si_filters["posting_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		si_filters["posting_date"] = ["<=", filters.to_date]

	# permission-checked (get_list): role read-perm + User Permissions scope the rows.
	invoices = frappe.get_list(
		"Sales Invoice",
		filters=si_filters,
		fields=[
			"name", "posting_date", "customer", "due_date",
			"grand_total", "outstanding_amount", "status", "currency",
		],
		order_by="posting_date desc, name desc",
	)

	today = getdate(nowdate())
	rows = []
	for si in invoices:
		is_overdue = bool(si.due_date and getdate(si.due_date) < today and flt(si.outstanding_amount) > 0)
		rows.append({
			"name": si.name,
			"posting_date": si.posting_date,
			"customer": si.customer,
			"due_date": si.due_date,
			"grand_total": flt(si.grand_total),
			"outstanding_amount": flt(si.outstanding_amount),
			"status": si.status,
			"overdue": _("Overdue") if is_overdue else "",
			"currency": si.currency,
		})
	return rows
