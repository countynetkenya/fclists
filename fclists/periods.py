"""fclists.periods — thin server-side companion for the "Report period" preset filter
(fclists/public/js/fclists_periods.js). Every preset resolves entirely client-side via native
frappe.datetime primitives EXCEPT the two FISCAL-anchored ones ("Next fiscal quarter" / "Next financial
year"), which need `erpnext.accounts.utils.get_fiscal_year` — that reads the Fiscal Year doctype, which is
not available client-side — so those two make ONE whitelisted round-trip here.

ANTI-REINVENTION (CLAUDE.md rule #1): never hand-roll fiscal math. This anchors on the NATIVE
`erpnext.accounts.utils.get_fiscal_year` (name, start, end) tuple and steps with native
`frappe.utils.add_days`/`add_months`. If no Fiscal Year is configured (or erpnext's fiscal lookup fails for
any reason), it falls back to the calendar equivalent via `frappe.utils.get_timespan_date_range` — the
preset ALWAYS resolves, never a crash.

Community law (D-048/D-049): fclists stays required_apps=["erpnext"] — this is FCLists' OWN thin copy of
the same fiscal-anchor pattern fcreports/fcreports/periods.py's `_fiscal()` composes; never a cross-app
import (each app carries its own copy, like fcbi already duplicates the company-scope helpers).
"""
import frappe
from frappe.utils import add_days, add_months, get_timespan_date_range, getdate


def _d(x):
	"""Coerce any native date/datetime/str into a 'YYYY-MM-DD' string (getdate normalises)."""
	return getdate(x).isoformat()


@frappe.whitelist()
def resolve_fiscal_period(key, company=None):
	"""(from_date, to_date) 'YYYY-MM-DD' strings for the two fiscal-anchored presets. `key` in
	{'next_fiscal_quarter', 'next_financial_year'}; anything else returns None (defensive — the JS caller
	never sends another key, but this stays honest under direct API use). Falls back to the calendar
	equivalent on any lookup failure — never a crash."""
	if key not in ("next_fiscal_quarter", "next_financial_year"):
		return None

	today = getdate()
	want = "quarter" if key == "next_fiscal_quarter" else "year"

	try:
		from erpnext.accounts.utils import get_fiscal_year

		_, fy_start, fy_end = get_fiscal_year(today, company=company)
		fy_start, fy_end = getdate(fy_start), getdate(fy_end)

		if want == "year":
			# Next financial year = the fiscal year starting the day after this one ends.
			_, n_start, n_end = get_fiscal_year(add_days(fy_end, 1), company=company)
			return {"from_date": _d(n_start), "to_date": _d(n_end)}

		# want == "quarter": split THIS fiscal year into four 3-month segments from fy_start; step +1.
		months_in = (today.year * 12 + today.month) - (fy_start.year * 12 + fy_start.month)
		q_index = months_in // 3
		n_start = add_months(fy_start, (q_index + 1) * 3)
		n_end = add_days(add_months(n_start, 3), -1)
		return {"from_date": _d(n_start), "to_date": _d(n_end)}
	except Exception:  # noqa: BLE001 — no erpnext / no fiscal year configured -> calendar fallback
		span = "next quarter" if want == "quarter" else "next year"
		s, e = get_timespan_date_range(span)
		return {"from_date": _d(s), "to_date": _d(e)}
