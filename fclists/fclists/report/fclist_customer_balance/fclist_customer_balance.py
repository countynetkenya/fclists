"""FClist Customer Balance — the QuickBooks 3-field AR board per customer (AR density parity).

One row per customer with money owed: OUTSTANDING (total AR = sum of submitted Sales Invoice
outstanding_amount), CREDIT LIMIT (Customer.credit_limit — the global limit row), AVAILABLE CREDIT
(limit − outstanding, floored at 0 when a limit is set), and PAST DUE (the overdue portion —
outstanding on invoices whose due_date < today). QuickBooks shows exactly these at a glance; the
native Customer list cannot, because every figure is derived by aggregating Sales Invoice rows against
today's date. This Script Report is the native tool.

Security (Finding B): ORM-only (frappe.get_all) → User Permissions on Customer / Sales Invoice are
enforced automatically. No raw SQL, so no build_match_conditions needed. Role-gated on the Report doc
(native Accounts roles + System Manager) — never world-readable.

v16-safe: sums are done in PYTHON (frappe.get_all rejects "sum(x) as y" field strings); every query
passes an explicit order_by. Sector-neutral (no client literal); config-driven.
"""
import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 220},
		{"label": _("Customer Name"), "fieldname": "customer_name", "fieldtype": "Data", "width": 200},
		{"label": _("Outstanding"), "fieldname": "outstanding", "fieldtype": "Currency", "width": 140},
		{"label": _("Credit Limit"), "fieldname": "credit_limit", "fieldtype": "Currency", "width": 140},
		{"label": _("Available Credit"), "fieldname": "available_credit", "fieldtype": "Currency", "width": 150},
		{"label": _("Past Due"), "fieldname": "past_due", "fieldtype": "Currency", "width": 140},
	]


def _data(filters):
	# --- outstanding AR per customer, aggregated in PYTHON from submitted Sales Invoices --------------
	si_filters = {"docstatus": 1, "outstanding_amount": [">", 0]}
	if filters.get("company"):
		si_filters["company"] = filters.company
	if filters.get("customer"):
		si_filters["customer"] = filters.customer

	invoices = frappe.get_all(
		"Sales Invoice",
		filters=si_filters,
		fields=["customer", "outstanding_amount", "due_date"],
		order_by="customer asc",
	)

	today = getdate(nowdate())
	outstanding = {}
	past_due = {}
	for si in invoices:
		cust = si.customer
		amt = flt(si.outstanding_amount)
		outstanding[cust] = flt(outstanding.get(cust, 0)) + amt
		if si.due_date and getdate(si.due_date) < today:
			past_due[cust] = flt(past_due.get(cust, 0)) + amt

	if not outstanding:
		return []

	# --- credit limit per customer (Customer.credit_limit — the global limit row) --------------------
	cust_names = list(outstanding.keys())
	credit_limit = {}
	customer_name = {}
	for c in frappe.get_all(
		"Customer",
		filters={"name": ["in", cust_names]},
		fields=["name", "customer_name"],
		order_by="name asc",
	):
		customer_name[c.name] = c.customer_name

	# Credit limit lives on the child table `Customer Credit Limit` (per company) in v16 — NOT on Customer.
	# Prefer the row matching the filtered company; else the first non-zero limit seen (company-agnostic).
	company = filters.get("company")
	for cl in frappe.get_all(
		"Customer Credit Limit",
		filters={"parent": ["in", cust_names], "parenttype": "Customer"},
		fields=["parent", "company", "credit_limit"],
		order_by="parent asc",
	):
		lim = flt(cl.credit_limit)
		if not lim:
			continue
		if company and cl.company == company:
			credit_limit[cl.parent] = lim
		elif cl.parent not in credit_limit:
			credit_limit[cl.parent] = lim

	# --- assemble; order by outstanding desc (biggest debtors first) ----------------------------------
	rows = []
	for cust, out in outstanding.items():
		limit = flt(credit_limit.get(cust, 0))
		# Available credit only meaningful when a limit is set; floor at 0 (never show negative headroom).
		available = max(limit - out, 0.0) if limit else 0.0
		rows.append({
			"customer": cust,
			"customer_name": customer_name.get(cust, cust),
			"outstanding": flt(out),
			"credit_limit": limit,
			"available_credit": available,
			"past_due": flt(past_due.get(cust, 0)),
		})
	rows.sort(key=lambda r: r["outstanding"], reverse=True)
	return rows
