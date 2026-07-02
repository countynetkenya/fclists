"""FClist Returns — credit-notes / sales returns board (QBO-POS density parity).

Every Sales Invoice with `is_return = 1` (a credit note): date, customer, the invoice it was returned against,
grand total (negative, as ERPNext stores returns), and status. The one screen a manager uses to audit refunds.

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
		{"label": _("Credit Note"), "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 200},
		{"label": _("Return Against"), "fieldname": "return_against", "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
		{"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 90},
	]


def _data(filters):
	si_filters = {"docstatus": 1, "is_return": 1}
	if filters.get("company"):
		si_filters["company"] = filters.company
	if filters.get("customer"):
		si_filters["customer"] = filters.customer
	if filters.get("from_date") and filters.get("to_date"):
		si_filters["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		si_filters["posting_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		si_filters["posting_date"] = ["<=", filters.to_date]

	returns = frappe.get_all(
		"Sales Invoice",
		filters=si_filters,
		fields=[
			"name", "posting_date", "customer", "return_against",
			"grand_total", "status", "currency",
		],
		order_by="posting_date desc, name desc",
	)

	rows = []
	for r in returns:
		rows.append({
			"name": r.name,
			"posting_date": r.posting_date,
			"customer": r.customer,
			"return_against": r.return_against,
			"grand_total": flt(r.grand_total),
			"status": r.status,
			"currency": r.currency,
		})
	return rows
