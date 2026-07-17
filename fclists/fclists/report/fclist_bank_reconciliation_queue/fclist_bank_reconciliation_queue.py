"""FClist Bank Reconciliation Queue — deposits/withdrawals AWAITING reconciliation (QBO "For Review" parity).

Every submitted Payment Entry that has NOT yet been cleared (native `clearance_date IS NULL`) — i.e. the
bank/cash/mobile-money movements still sitting in the reconciliation queue. Generic to bank AND mobile-money:
it reads ONLY native Payment Entry fields (mode_of_payment, reference_no, paid_amount), so an M-PESA deposit
booked as a Payment Entry appears here with no titan/settle dependency whatsoever.

Security (Finding B): role-gated on its Report doc (native Accounts roles + System Manager) — never
world-readable. The row query runs through frappe.get_list → read permission is checked and User
Permissions scope the rows (a user permitted to Company A never sees Company B's queue). No raw SQL,
so no build_match_conditions needed.

v16-safe: explicit order_by (posting_date desc, creation desc); no grouped-sum field strings. Sector-neutral
(no client literal — reads native Payment Entry only).

Companies / Cost Centre (2026-07-17 tree-checkbox yokoten — see fclists.nav_options, thin copy of
fcbi/fcbi/consolidate.py's pattern): `companies` MultiSelectList wins over the legacy single `company`
Link; `cost_center` filters Payment Entry's own header cost_center field — bench-proven present on
Payment Entry (same fact that overturned fclist_payments.py's wave-1 exclusion).
"""
import frappe
from frappe import _

from fclists.nav_options import resolve_companies_filter, resolve_cost_centre_filter


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Payment Entry"), "fieldname": "name", "fieldtype": "Link", "options": "Payment Entry", "width": 170},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Type"), "fieldname": "payment_type", "fieldtype": "Data", "width": 100},
		{"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data", "width": 100},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 180},
		{"label": _("Paid Amount"), "fieldname": "paid_amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Mode of Payment"), "fieldname": "mode_of_payment", "fieldtype": "Link", "options": "Mode of Payment", "width": 140},
		{"label": _("Reference No"), "fieldname": "reference_no", "fieldtype": "Data", "width": 150},
		{"label": _("Reference Date"), "fieldname": "reference_date", "fieldtype": "Date", "width": 110},
		{"label": _("Bank/Cash Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 240},
	]


def _data(filters):
	# Unreconciled = submitted Payment Entry with no clearance_date. Read native fields only.
	pe_filters = {"docstatus": 1, "clearance_date": ["is", "not set"]}
	companies = resolve_companies_filter(filters.get("companies"), filters.get("company"))
	if companies:
		pe_filters["company"] = ["in", companies]
	cost_centers = resolve_cost_centre_filter(filters.get("cost_center"))
	if cost_centers:
		pe_filters["cost_center"] = ["in", cost_centers]
	if filters.get("mode_of_payment"):
		pe_filters["mode_of_payment"] = filters.mode_of_payment
	if filters.get("from_date") and filters.get("to_date"):
		pe_filters["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		pe_filters["posting_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		pe_filters["posting_date"] = ["<=", filters.to_date]

	# permission-checked (get_list): role read-perm + User Permissions scope the rows.
	entries = frappe.get_list(
		"Payment Entry",
		filters=pe_filters,
		fields=[
			"name", "posting_date", "payment_type", "party_type", "party",
			"paid_amount", "received_amount", "mode_of_payment", "reference_no",
			"reference_date", "paid_from", "paid_to",
		],
		order_by="posting_date desc, creation desc",
	)

	rows = []
	for pe in entries:
		# Bank/cash side depends on direction: money leaves paid_from (Pay) or lands in paid_to (Receive).
		account = pe.paid_from if pe.payment_type == "Pay" else pe.paid_to
		rows.append({
			"name": pe.name,
			"posting_date": pe.posting_date,
			"payment_type": pe.payment_type,
			"party_type": pe.party_type,
			"party": pe.party,
			"paid_amount": pe.paid_amount if pe.payment_type == "Pay" else pe.received_amount,
			"mode_of_payment": pe.mode_of_payment,
			"reference_no": pe.reference_no,
			"reference_date": pe.reference_date,
			"account": account,
		})
	return rows
