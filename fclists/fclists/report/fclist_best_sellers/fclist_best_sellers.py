"""FClist Best Sellers — velocity / sales-rank board (units sold over a window, rolled up to Item).

Top items by UNITS SOLD over a filterable window (Jason-confirmed: velocity = sales-rank). Per item:
rank, item_code, item_name, item_group, qty_sold, revenue, margin. The native item list cannot rank by
units moved (it is derived from submitted Sales Invoice lines over a window), so this Script Report is the
native tool.

Security (Finding B): role-gated on the Report doc (native Stock/Accounts roles + System Manager) —
never world-readable. The row-driving Sales Invoice query runs through frappe.get_list → read permission
is checked and User Permissions scope the rows; a role admitted by the Report doc but WITHOUT Sales
Invoice read permission gets an empty board (never a leak). Line/valuation lookups then read only for
those already-permitted invoices/items.
v16-safe: sums grouped in PYTHON (frappe.get_all rejects "sum(x) as y" field strings); every query passes
an explicit order_by. Sector-neutral (no client literal).

Companies / Cost Centre (2026-07-17 tree-checkbox yokoten — see fclists.nav_options, thin copy of
fcbi/fcbi/consolidate.py's pattern): `companies` MultiSelectList wins over the legacy single `company`
Link; `cost_center` filters Sales Invoice's own header cost_center field — both applied to the invoice-
selecting query, same as fclist_sales_invoice.py.
"""
import frappe
from frappe import _
from frappe.utils import flt, cint, add_days, nowdate

from fclists.nav_options import resolve_companies_filter, resolve_cost_centre_filter


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Rank"), "fieldname": "rank", "fieldtype": "Int", "width": 70},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 160},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 140},
		{"label": _("Qty Sold"), "fieldname": "qty_sold", "fieldtype": "Float", "width": 110},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 130},
		{"label": _("Margin"), "fieldname": "margin", "fieldtype": "Currency", "width": 130},
	]


def _data(filters):
	days = cint(filters.get("window_days")) or 30
	from_date = add_days(nowdate(), -days)

	si_filters = {"docstatus": 1, "posting_date": [">=", from_date], "is_return": 0}
	companies = resolve_companies_filter(filters.get("companies"), filters.get("company"))
	if companies:
		si_filters["company"] = ["in", companies]
	cost_centers = resolve_cost_centre_filter(filters.get("cost_center"))
	if cost_centers:
		si_filters["cost_center"] = ["in", cost_centers]
	# The Report doc also admits Stock roles, which natively lack Sales Invoice read — degrade to an
	# empty board for them rather than leak (or hard-error on) sales rows they cannot read.
	if not frappe.has_permission("Sales Invoice"):
		return []
	# permission-checked (get_list): role read-perm + User Permissions scope the invoice set.
	invoices = frappe.get_list(
		"Sales Invoice", filters=si_filters, fields=["name"], order_by="posting_date desc"
	)
	if not invoices:
		return []
	inv_names = [i.name for i in invoices]

	line_filters = {"parent": ["in", inv_names]}
	if filters.get("item_group"):
		line_filters["item_group"] = filters.item_group

	# aggregate qty / revenue / cost per item_code in PYTHON (no "sum(x) as y" field strings).
	# get_all here is safe: child rows scoped to parents from the permission-checked get_list above.
	qty = {}
	revenue = {}
	meta = {}
	for li in frappe.get_all(
		"Sales Invoice Item",
		filters=line_filters,
		fields=[
			"item_code", "item_name", "item_group",
			"stock_qty", "qty", "base_net_amount", "amount",
		],
		order_by="parent asc",
	):
		code = li.item_code
		if not code:
			continue
		q = flt(li.stock_qty) or flt(li.qty)
		rev = flt(li.base_net_amount) or flt(li.amount)
		qty[code] = flt(qty.get(code, 0)) + q
		revenue[code] = flt(revenue.get(code, 0)) + rev
		meta.setdefault(code, {"item_name": li.item_name, "item_group": li.item_group})

	if not qty:
		return []

	# Margin basis: value the sold qty at the item's current stock valuation (Bin) — a robust COGS proxy
	# that avoids the version-fragile per-line cost field. Best-effort; 0 when the item carries no stock/
	# valuation. Bin.valuation_rate is the same field the Item Stock report already reads successfully.
	# get_all here is safe: a valuation ATTRIBUTE of items already on permitted invoice lines.
	cost = {}
	val = {}
	for b in frappe.get_all(
		"Bin",
		filters={"item_code": ["in", list(qty.keys())]},
		fields=["item_code", "valuation_rate", "actual_qty"],
		order_by="item_code asc",
	):
		v = flt(b.valuation_rate)
		if v <= 0:
			continue
		prev = val.get(b.item_code)
		# keep the valuation from the warehouse holding the most stock (most representative)
		if prev is None or flt(b.actual_qty) > prev[1]:
			val[b.item_code] = (v, flt(b.actual_qty))
	for code in qty:
		cost[code] = flt(val.get(code, (0, 0))[0]) * flt(qty[code])

	# rank by units sold (velocity) desc, tie-break by revenue desc then item_code asc
	ordered = sorted(
		qty.keys(),
		key=lambda c: (-flt(qty[c]), -flt(revenue.get(c, 0)), c),
	)

	top_n = cint(filters.get("top_n")) or 0
	if top_n > 0:
		ordered = ordered[:top_n]

	rows = []
	for idx, code in enumerate(ordered, start=1):
		rev = flt(revenue.get(code, 0))
		rows.append({
			"rank": idx,
			"item_code": code,
			"item_name": meta.get(code, {}).get("item_name"),
			"item_group": meta.get(code, {}).get("item_group"),
			"qty_sold": flt(qty.get(code, 0)),
			"revenue": rev,
			"margin": rev - flt(cost.get(code, 0)),
		})
	return rows
