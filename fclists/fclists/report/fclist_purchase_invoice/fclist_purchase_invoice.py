"""FClist Purchase Invoice — dense AP board, the mirror of FClist Sales Invoice (A/P density parity).

A single glance at every purchase invoice: date, supplier, total, what is still outstanding, its
status, and a computed OVERDUE flag (due_date < today AND outstanding_amount > 0). The native Purchase
Invoice list cannot show an "overdue" column because it is derived from two fields against today's date
— this Script Report is the native tool.

Security (Finding B): role-gated on the Report doc (native Accounts roles + System Manager) — never
world-readable. The row query runs through frappe.get_list → read permission is checked and User
Permissions scope the rows (a user permitted to Company A never sees Company B's AP). No raw SQL,
so no build_match_conditions needed.

v16-safe: explicit order_by; no grouped-sum field strings (overdue derived per row in Python).
Sector-neutral; config-driven.
"""
import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Invoice"), "fieldname": "name", "fieldtype": "Link", "options": "Purchase Invoice", "width": 170},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 210},
		{"label": _("Due Date"), "fieldname": "due_date", "fieldtype": "Date", "width": 100},
		{"label": _("Grand Total"), "fieldname": "grand_total", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Outstanding"), "fieldname": "outstanding_amount", "fieldtype": "Currency", "options": "currency", "width": 130},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("Overdue"), "fieldname": "overdue", "fieldtype": "Data", "width": 90},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 90},
	]


def _data(filters):
	pi_filters = {"docstatus": 1}
	if filters.get("company"):
		pi_filters["company"] = filters.company
	if filters.get("supplier"):
		pi_filters["supplier"] = filters.supplier
	if filters.get("status"):
		pi_filters["status"] = filters.status
	if filters.get("from_date") and filters.get("to_date"):
		pi_filters["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		pi_filters["posting_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		pi_filters["posting_date"] = ["<=", filters.to_date]

	# permission-checked (get_list): role read-perm + User Permissions scope the rows.
	invoices = frappe.get_list(
		"Purchase Invoice",
		filters=pi_filters,
		fields=[
			"name", "posting_date", "supplier", "due_date",
			"grand_total", "outstanding_amount", "status", "currency",
		],
		order_by="posting_date desc, name desc",
	)

	today = getdate(nowdate())
	rows = []
	for pi in invoices:
		is_overdue = bool(pi.due_date and getdate(pi.due_date) < today and flt(pi.outstanding_amount) > 0)
		rows.append({
			"name": pi.name,
			"posting_date": pi.posting_date,
			"supplier": pi.supplier,
			"due_date": pi.due_date,
			"grand_total": flt(pi.grand_total),
			"outstanding_amount": flt(pi.outstanding_amount),
			"status": pi.status,
			"overdue": _("Overdue") if is_overdue else "",
			"currency": pi.currency,
		})
	return rows
