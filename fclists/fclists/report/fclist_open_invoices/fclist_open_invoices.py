"""FClist Open Invoices — unpaid Sales Invoices with AR AGING BUCKETS (QuickBooks A/R Aging parity).

One row per unpaid (outstanding > 0), submitted Sales Invoice, tagged with the aging bucket computed
in PYTHON from due_date vs today: Current (not yet due), 1-30, 31-60, 61-90, 90+ days past due. This is
the classic A/R aging worklist a collections clerk works down; the native Sales Invoice list cannot
derive the bucket (it depends on today's date against due_date).

Security (Finding B): ORM-only (frappe.get_all) → User Permissions enforced automatically. No raw SQL,
so no build_match_conditions needed. Role-gated on the Report doc (native Accounts roles + System
Manager) — never world-readable.

v16-safe: explicit order_by; no grouped-sum field strings (buckets computed per row in Python).
Sector-neutral; config-driven.
"""
import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate, date_diff


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Invoice"), "fieldname": "invoice", "fieldtype": "Link", "options": "Sales Invoice", "width": 170},
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 210},
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{"label": _("Due Date"), "fieldname": "due_date", "fieldtype": "Date", "width": 110},
		{"label": _("Outstanding"), "fieldname": "outstanding", "fieldtype": "Currency", "options": "currency", "width": 140},
		{"label": _("Days Past Due"), "fieldname": "days_past_due", "fieldtype": "Int", "width": 120},
		{"label": _("Bucket"), "fieldname": "bucket", "fieldtype": "Data", "width": 100},
		{"label": _("Currency"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "width": 90},
	]


def _bucket(days_past_due):
	# days_past_due <= 0 means not yet due (Current).
	if days_past_due <= 0:
		return _("Current")
	if days_past_due <= 30:
		return _("1-30")
	if days_past_due <= 60:
		return _("31-60")
	if days_past_due <= 90:
		return _("61-90")
	return _("90+")


def _data(filters):
	si_filters = {"docstatus": 1, "outstanding_amount": [">", 0]}
	if filters.get("company"):
		si_filters["company"] = filters.company
	if filters.get("customer"):
		si_filters["customer"] = filters.customer

	invoices = frappe.get_all(
		"Sales Invoice",
		filters=si_filters,
		fields=["name", "customer", "posting_date", "due_date", "outstanding_amount", "currency"],
		order_by="due_date asc, name asc",
	)

	today = getdate(nowdate())
	rows = []
	for si in invoices:
		if si.due_date:
			dpd = date_diff(today, getdate(si.due_date))  # positive => overdue by this many days
		else:
			dpd = 0
		rows.append({
			"invoice": si.name,
			"customer": si.customer,
			"posting_date": si.posting_date,
			"due_date": si.due_date,
			"outstanding": flt(si.outstanding_amount),
			"days_past_due": dpd if dpd > 0 else 0,
			"bucket": _bucket(dpd),
			"currency": si.currency,
		})
	return rows
