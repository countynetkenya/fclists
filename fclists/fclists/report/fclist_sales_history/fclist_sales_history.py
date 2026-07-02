"""FClist Sales History — the QuickBooks "Sales History" screen for ERPNext.

A chronological list of every sales receipt (Sales Invoice, including POS via `is_pos`) with a link column
to open/print each one, filterable by date-range, customer, and owner (the cashier who rang it). This is the
reprint / lookup screen a till operator or manager reaches for at end of day.

The "Print" column is a Link to the Sales Invoice; the desk's built-in "Print" action on the opened form does
the actual receipt reprint — we do not rebuild printing (anti-reinvention).

Security: ORM-only (frappe.get_all) → User Permissions enforced automatically (Finding B). No raw SQL, so no
build_match_conditions needed. Role-gated on its Report doc (native Accounts roles + System Manager).
v16-safe: explicit order_by; read-only; no grouped-sum field strings.
"""
import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Receipt"), "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Time"), "fieldname": "posting_time", "fieldtype": "Time", "width": 90},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 190},
		{"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "options": "currency", "width": 120},
		{"label": _("POS"), "fieldname": "pos_flag", "fieldtype": "Data", "width": 70},
		{"label": _("Cashier"), "fieldname": "owner", "fieldtype": "Link", "options": "User", "width": 180},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Print / Open"), "fieldname": "print_link", "fieldtype": "Link", "options": "Sales Invoice", "width": 140},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 90},
	]


def _data(filters):
	si_filters = {"docstatus": 1}
	if filters.get("company"):
		si_filters["company"] = filters.company
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

	invoices = frappe.get_all(
		"Sales Invoice",
		filters=si_filters,
		fields=[
			"name", "posting_date", "posting_time", "customer", "grand_total",
			"is_pos", "owner", "status", "currency",
		],
		order_by="posting_date desc, posting_time desc, name desc",
	)

	rows = []
	for si in invoices:
		rows.append({
			"name": si.name,
			"posting_date": si.posting_date,
			"posting_time": si.posting_time,
			"customer": si.customer,
			"grand_total": flt(si.grand_total),
			"pos_flag": _("POS") if si.is_pos else "",
			"owner": si.owner,
			"status": si.status,
			"print_link": si.name,
			"currency": si.currency,
		})
	return rows
