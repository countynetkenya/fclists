"""FClist Sales by Cashier — sales grouped by the invoice owner (the cashier / session user).

Per cashier over a date range: invoice_count, total_sales, avg_sale. The `owner` of a Sales Invoice is the
user who created it — in a POS/counter workflow that is the cashier who rang the sale. The native list has
no "group by owner with sum + average" view, so this Script Report is the native tool.

Security (Finding B): role-gated on the Report doc (native Accounts roles + System Manager) — never
world-readable. The row query runs through frappe.get_list → read permission is checked and User
Permissions scope the rows. No raw SQL, so no build_match_conditions needed.
v16-safe: sums/averages grouped in PYTHON (frappe.get_all rejects "sum(x) as y" field strings); every query
passes an explicit order_by. Sector-neutral (no client literal).

Companies / Cost Centre (2026-07-17 tree-checkbox yokoten — see fclists.nav_options, thin copy of
fcbi/fcbi/consolidate.py's pattern): `companies` MultiSelectList wins over the legacy single `company`
Link; `cost_center` filters Sales Invoice's own header cost_center field.
"""
import frappe
from frappe import _
from frappe.utils import flt

from fclists.nav_options import resolve_companies_filter, resolve_cost_centre_filter


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Cashier"), "fieldname": "cashier", "fieldtype": "Link", "options": "User", "width": 240},
		{"label": _("Invoices"), "fieldname": "invoice_count", "fieldtype": "Int", "width": 110},
		{"label": _("Total Sales"), "fieldname": "total_sales", "fieldtype": "Currency", "width": 150},
		{"label": _("Avg Sale"), "fieldname": "avg_sale", "fieldtype": "Currency", "width": 150},
	]


def _data(filters):
	si_filters = {"docstatus": 1}
	companies = resolve_companies_filter(filters.get("companies"), filters.get("company"))
	if companies:
		si_filters["company"] = ["in", companies]
	cost_centers = resolve_cost_centre_filter(filters.get("cost_center"))
	if cost_centers:
		si_filters["cost_center"] = ["in", cost_centers]
	if filters.get("from_date") and filters.get("to_date"):
		si_filters["posting_date"] = ["between", [filters.from_date, filters.to_date]]
	elif filters.get("from_date"):
		si_filters["posting_date"] = [">=", filters.from_date]
	elif filters.get("to_date"):
		si_filters["posting_date"] = ["<=", filters.to_date]

	# permission-checked (get_list): role read-perm + User Permissions scope the rows.
	invoices = frappe.get_list(
		"Sales Invoice",
		filters=si_filters,
		fields=["owner", "grand_total"],
		order_by="owner asc",
	)
	if not invoices:
		return []

	# group by owner in PYTHON (no "sum(x) as y" field strings)
	count = {}
	total = {}
	for si in invoices:
		owner = si.owner
		count[owner] = count.get(owner, 0) + 1
		total[owner] = flt(total.get(owner, 0)) + flt(si.grand_total)

	# order by total_sales desc, tie-break cashier asc
	ordered = sorted(count.keys(), key=lambda o: (-flt(total.get(o, 0)), o))

	rows = []
	for owner in ordered:
		n = count.get(owner, 0)
		tot = flt(total.get(owner, 0))
		rows.append({
			"cashier": owner,
			"invoice_count": n,
			"total_sales": tot,
			"avg_sale": (tot / n) if n else 0.0,
		})
	return rows
