"""FClist Supplier Balance — the AP mirror of Customer Balance (A/P density parity).

One row per supplier we owe: OUTSTANDING (total A/P = sum of submitted Purchase Invoice
outstanding_amount) and the PAST DUE portion (outstanding on invoices whose due_date < today). This is
the QuickBooks "A/P Aging Summary" glance a payables clerk works down. The native Supplier list cannot
show it — every figure is derived by aggregating Purchase Invoice rows against today's date.

Security (Finding B): role-gated on the Report doc (native Accounts roles + System Manager) — never
world-readable. The row-driving Purchase Invoice query runs through frappe.get_list → read permission
is checked and User Permissions scope the rows (a user permitted to Company A never sees Company B's
AP); the name lookup then reads only suppliers already on those permitted invoices. No raw SQL, so no
build_match_conditions needed.

v16-safe: sums are done in PYTHON; every query passes an explicit order_by. Sector-neutral; config-driven.

Companies (2026-07-17 tree-checkbox yokoten — see fclists.nav_options, thin copy of
fcbi/fcbi/consolidate.py's pattern): `companies` MultiSelectList wins over the legacy single `company`
Link. No Cost Centre filter this wave — ref_doctype is Supplier, a MASTER doctype with no cost_center
column of its own; see the yokoten applicability table.
"""
import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from fclists.nav_options import resolve_companies_filter


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
	companies = resolve_companies_filter(filters.get("companies"), filters.get("company"))
	if companies:
		pi_filters["company"] = ["in", companies]
	if filters.get("supplier"):
		pi_filters["supplier"] = filters.supplier

	# permission-checked (get_list): role read-perm + User Permissions scope the AP rows.
	invoices = frappe.get_list(
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

	# get_all here is safe: names are ATTRIBUTES of suppliers already on permitted invoices above.
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
