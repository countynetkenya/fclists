"""FClist Sales YoY — the QuickBooks dashboard: Today / WTD / MTD / YTD this year vs same period last year.

Four rows (Today, Week to Date, Month to Date, Year to Date). For each: this-year sales, last-year sales
over the SAME calendar period (same start-of-period → same offset-from-today one year back), and the %
change. Windows are computed in PYTHON from posting_date so there are no raw-SQL date expressions.

Security (Finding B): ORM-only (frappe.get_all) → User Permissions enforced automatically. No raw SQL, so
no build_match_conditions needed. Role-gated on the Report doc (native Accounts roles + System Manager) —
never world-readable.
v16-safe: sums grouped in PYTHON (frappe.get_all rejects "sum(x) as y" field strings); every query passes
an explicit order_by. Sector-neutral (no client literal).
"""
import datetime

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Period"), "fieldname": "period", "fieldtype": "Data", "width": 160},
		{"label": _("This Year"), "fieldname": "this_year", "fieldtype": "Currency", "width": 160},
		{"label": _("Last Year"), "fieldname": "last_year", "fieldtype": "Currency", "width": 160},
		{"label": _("Change"), "fieldname": "change", "fieldtype": "Currency", "width": 150},
		{"label": _("Change %"), "fieldname": "change_pct", "fieldtype": "Percent", "width": 120},
	]


def _shift_year(d, years):
	"""Shift a date back/forward whole years, guarding Feb-29 (→ Feb-28)."""
	try:
		return d.replace(year=d.year + years)
	except ValueError:
		return d.replace(month=2, day=28, year=d.year + years)


def _periods(today):
	"""Return [(label, this_start, this_end, last_start, last_end), ...] — all inclusive date windows.

	Last-year windows are the same calendar span shifted back exactly one year (so WTD/MTD/YTD compare
	like-for-like: same weekday offset, same day-of-month, same day-of-year).
	"""
	# Today
	rows = [(_("Today"), today, today)]
	# Week to date — ISO week (Monday start)
	week_start = today - datetime.timedelta(days=today.weekday())
	rows.append((_("Week to Date"), week_start, today))
	# Month to date
	rows.append((_("Month to Date"), today.replace(day=1), today))
	# Year to date
	rows.append((_("Year to Date"), today.replace(month=1, day=1), today))

	out = []
	for label, start, end in rows:
		out.append((label, start, end, _shift_year(start, -1), _shift_year(end, -1)))
	return out


def _sum_sales(company, start, end):
	si_filters = {"docstatus": 1, "posting_date": ["between", [start, end]]}
	if company:
		si_filters["company"] = company
	invoices = frappe.get_all(
		"Sales Invoice",
		filters=si_filters,
		fields=["grand_total"],
		order_by="posting_date asc",
	)
	# sum in PYTHON (no "sum(x) as y" field strings)
	return flt(sum(flt(si.grand_total) for si in invoices))


def _data(filters):
	company = filters.get("company")
	today = getdate(nowdate())

	rows = []
	for label, ty_start, ty_end, ly_start, ly_end in _periods(today):
		ty = _sum_sales(company, ty_start, ty_end)
		ly = _sum_sales(company, ly_start, ly_end)
		change = ty - ly
		rows.append({
			"period": label,
			"this_year": ty,
			"last_year": ly,
			"change": change,
			"change_pct": flt(change / ly * 100.0, 2) if ly else 0.0,
		})
	return rows
