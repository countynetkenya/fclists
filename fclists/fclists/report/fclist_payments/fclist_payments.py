"""FClist Payments — payments RECEIVED board (QBO-POS "Received Payments" parity).

Every incoming Payment Entry (payment_type = Receive): posting_date, party, paid_amount, mode_of_payment,
reference_no (the bank / M-Pesa transaction ref), and reference_date. The screen a bursar/cashier uses to
reconcile the day's collections against the bank/M-Pesa statement.

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
		{"label": _("Payment"), "fieldname": "name", "fieldtype": "Link", "options": "Payment Entry", "width": 170},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data", "width": 110},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 200},
		{"label": _("Paid Amount"), "fieldname": "paid_amount", "fieldtype": "Currency", "options": "paid_to_account_currency", "width": 130},
		{"label": _("Mode"), "fieldname": "mode_of_payment", "fieldtype": "Link", "options": "Mode of Payment", "width": 140},
		{"label": _("Reference No"), "fieldname": "reference_no", "fieldtype": "Data", "width": 160},
		{"label": _("Reference Date"), "fieldname": "reference_date", "fieldtype": "Date", "width": 120},
		{"label": _("Currency"), "fieldname": "paid_to_account_currency", "fieldtype": "Link", "options": "Currency", "width": 90},
	]


def _data(filters):
	pe_filters = {"docstatus": 1, "payment_type": "Receive"}
	if filters.get("company"):
		pe_filters["company"] = filters.company
	if filters.get("mode_of_payment"):
		pe_filters["mode_of_payment"] = filters.mode_of_payment
	if filters.get("party"):
		pe_filters["party"] = filters.party
	if filters.get("from_date") and filters.get("to_date"):
		pe_filters["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		pe_filters["posting_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		pe_filters["posting_date"] = ["<=", filters.to_date]

	payments = frappe.get_all(
		"Payment Entry",
		filters=pe_filters,
		fields=[
			"name", "posting_date", "party_type", "party", "paid_amount",
			"mode_of_payment", "reference_no", "reference_date", "paid_to_account_currency",
		],
		order_by="posting_date desc, name desc",
	)

	rows = []
	for p in payments:
		rows.append({
			"name": p.name,
			"posting_date": p.posting_date,
			"party_type": p.party_type,
			"party": p.party,
			"paid_amount": flt(p.paid_amount),
			"mode_of_payment": p.mode_of_payment,
			"reference_no": p.reference_no,
			"reference_date": p.reference_date,
			"paid_to_account_currency": p.paid_to_account_currency,
		})
	return rows
