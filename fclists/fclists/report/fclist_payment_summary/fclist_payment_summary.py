"""FClist Payment Summary — the day x tender-type reconciliation matrix (QB-POS "Payment Summary" parity).

One row per posting day; one Currency column per Mode of Payment actually used in the window, plus an
"On Account" column (the portion of the day's sales charged to the customer's account instead of tendered
at the till) and a Daily Total. This is the drawer/bank reconciliation screen a manager reads at the end of
a day, week or month — "how much came in as Cash vs M-Pesa vs on account, per day".

Semantics (faithful to the QB-POS screen): the matrix is about how the day's SALES were settled at the
moment of sale. POS tenders come from the Sales Invoice Payment child rows (net of change given); any
unpaid remainder — and the whole of a non-POS credit invoice — lands in "On Account". Payments collected
LATER against those accounts are a different screen: FClist Payments (Received Payments parity). Returns
flow through with their natural negative sign, exactly as QB-POS shows them.

Anti-reinvention: ERPNext's native "Sales Payment Summary" groups by invoice/mode but does not render the
QB-POS day x tender pivot with change-netting and an on-account column — this report is that thin delta,
composed from native Sales Invoice / Sales Invoice Payment / Mode of Payment only.

Security: ORM-only (frappe.get_all) → User Permissions enforced automatically (Finding B). No raw SQL, so
no build_match_conditions needed. Role-gated on its Report doc (native Accounts roles + System Manager).
v16-safe: explicit order_by; read-only; no grouped-sum field strings.
"""
import re

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	modes, rows = _data(filters)
	return _columns(modes), rows


def _mode_fieldname(mode):
	"""Stable, collision-safe row/column key for a Mode of Payment display name (pure)."""
	return "m_" + re.sub(r"[^a-z0-9]+", "_", (mode or "").lower()).strip("_")


def _net_tenders(payment_rows, change_amount, mode_types):
	"""Net an invoice's tender rows of the change handed back (pure).

	QB-POS shows what STAYED in the drawer; ERPNext's POS payment rows sum to grand_total +
	change_amount, with the change conventionally given from a Cash-type mode. Deduct the change
	from the first Cash-type row (falling back to the largest row when no Cash-type mode exists so
	the day still ties). Returns [(mode, net_amount)] with zero-amount rows dropped.
	"""
	rows = [[p.get("mode_of_payment"), flt(p.get("amount"))] for p in payment_rows]
	change = flt(change_amount)
	if change and rows:
		cash_rows = [r for r in rows if (mode_types or {}).get(r[0]) == "Cash"]
		target = cash_rows[0] if cash_rows else max(rows, key=lambda r: r[1])
		target[1] -= change
	return [(m, a) for m, a in rows if a]


def _columns(modes=None):
	cols = [
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
	]
	for mode in modes or []:
		cols.append({
			"label": mode,
			"fieldname": _mode_fieldname(mode),
			"fieldtype": "Currency",
			"width": 120,
		})
	cols += [
		{"label": _("On Account"), "fieldname": "on_account", "fieldtype": "Currency", "width": 120},
		{"label": _("Daily Total"), "fieldname": "daily_total", "fieldtype": "Currency", "width": 130},
	]
	return cols


def _data(filters):
	si_filters = {"docstatus": 1}
	if filters.get("company"):
		si_filters["company"] = filters.company
	if filters.get("from_date") and filters.get("to_date"):
		si_filters["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		si_filters["posting_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		si_filters["posting_date"] = ["<=", filters.to_date]

	invoices = frappe.get_all(
		"Sales Invoice",
		filters=si_filters,
		fields=["name", "posting_date", "is_pos", "grand_total", "change_amount"],
		order_by="posting_date asc, name asc",
	)

	pos_names = [si.name for si in invoices if si.is_pos]
	payments_by_parent = {}
	if pos_names:
		payment_rows = frappe.get_all(
			"Sales Invoice Payment",
			filters={"parenttype": "Sales Invoice", "parent": ["in", pos_names], "docstatus": 1},
			fields=["parent", "mode_of_payment", "amount"],
			order_by="parent asc, idx asc",
			parent_doctype="Sales Invoice",
		)
		for p in payment_rows:
			payments_by_parent.setdefault(p.parent, []).append(p)

	mode_types = {
		m.name: m.type
		for m in frappe.get_all("Mode of Payment", fields=["name", "type"], order_by="name asc")
	}

	# day -> {mode -> amount, "on_account": amount}
	days = {}
	mode_totals = {}
	for si in invoices:
		day = days.setdefault(si.posting_date, {"on_account": 0.0})
		tendered = 0.0
		for mode, amount in _net_tenders(payments_by_parent.get(si.name, []), si.change_amount, mode_types):
			day[mode] = flt(day.get(mode)) + amount
			mode_totals[mode] = flt(mode_totals.get(mode)) + amount
			tendered += amount
		# credit sale (non-POS) or the untendered remainder of a POS sale -> On Account
		day["on_account"] += flt(si.grand_total) - tendered

	# Columns ordered by tender volume (largest first), like the QB-POS screen reads
	modes = sorted(mode_totals, key=lambda m: abs(mode_totals[m]), reverse=True)

	rows = []
	for posting_date in sorted(days):
		day = days[posting_date]
		row = {"posting_date": posting_date, "on_account": flt(day["on_account"])}
		total = flt(day["on_account"])
		for mode in modes:
			amount = flt(day.get(mode))
			row[_mode_fieldname(mode)] = amount
			total += amount
		row["daily_total"] = total
		rows.append(row)
	return modes, rows
