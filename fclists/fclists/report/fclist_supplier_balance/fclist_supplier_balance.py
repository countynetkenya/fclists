"""FClist Supplier Balance — the AP mirror of Customer Balance (A/P density parity).

One row per supplier we owe: OUTSTANDING (total A/P = sum of submitted Purchase Invoice
outstanding_amount) and the PAST DUE portion (outstanding on invoices whose due_date < today). This is
the QuickBooks "A/P Aging Summary" glance a payables clerk works down. The native Supplier list cannot
show it — every figure is derived by aggregating Purchase Invoice rows against today's date.

Security (Finding B): ORM-only (frappe.get_all) → User Permissions on Supplier / Purchase Invoice are
enforced automatically. No raw SQL, so no build_match_conditions needed. Role-gated on the Report doc
(native Accounts roles + System Manager) — never world-readable.

v16-safe: sums are done in PYTHON; every query passes an explicit order_by. Sector-neutral; config-driven.
"""
import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Supplier"), "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 220},
		{"label": _("Supplier Name"), "fieldname": "supplier_name", "fieldtype": "Data", "width": 200},
		{"label": _("Outstanding"), "fieldname": "outstanding", "fieldtype": "Currency", "width": 150},
		{"label": _("Past Due"), "fieldname": "past_due", "fieldtype": "Currency", "width": 150},
	]


def _data(filters):
	pi_filters = {"docstatus": 1, "outstanding_amount": [">", 0]}
	if filters.get("company"):
		pi_filters["company"] = filters.company
	if filters.get("supplier"):
		pi_filters["supplier"] = filters.supplier

	invoices = frappe.get_all(
		"Purchase Invoice",
		filters=pi_filters,
		fields=["supplier", "outstanding_amount", "due_date"],
		order_by="supplier asc",
	)

	today = getdate(nowdate())
	outstanding = {}
	past_due = {}
	for pi in invoices:
		sup = pi.supplier
		amt = flt(pi.outstanding_amount)
		outstanding[sup] = flt(outstanding.get(sup, 0)) + amt
		if pi.due_date and getdate(pi.due_date) < today:
			past_due[sup] = flt(past_due.get(sup, 0)) + amt

	if not outstanding:
		return []

	sup_names = list(outstanding.keys())
	supplier_name = {}
	for s in frappe.get_all(
		"Supplier",
		filters={"name": ["in", sup_names]},
		fields=["name", "supplier_name"],
		order_by="name asc",
	):
		supplier_name[s.name] = s.supplier_name

	rows = []
	for sup, out in outstanding.items():
		rows.append({
			"supplier": sup,
			"supplier_name": supplier_name.get(sup, sup),
			"outstanding": flt(out),
			"past_due": flt(past_due.get(sup, 0)),
		})
	rows.sort(key=lambda r: r["outstanding"], reverse=True)
	return rows
