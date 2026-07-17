"""FClist Item Stock — dense on-hand + cost-plus + velocity board (QBO-POS "Item Stock" density parity).

Per item, live from native tables: on-hand qty (sum of tabBin.actual_qty across warehouses), valuation
rate, selling price (Item Price on the default selling price list), margin (price - valuation) and margin%,
reorder level, and UNITS SOLD in the last N days (velocity — sum of submitted Sales Invoice Item qty over a
filterable window). None of these can be shown by a plain list view, so this Script Report is the native
tool (docs/trystorm-fclists.md Finding D).

Security (Finding B): role-gated on its Report doc (never world-readable). The row-driving Item query
runs through frappe.get_list → read permission is checked and User Permissions scope the rows; on-hand /
price / reorder lookups then read only for those already-permitted items. The velocity column reads Sales
Invoice ONLY when the user holds read permission on it (Stock roles without it see 0, never a leak).

v16-safe: sums are done in PYTHON (frappe.get_all rejects "sum(x) as y" field strings); every query passes
an explicit order_by. Sector-neutral (no client literal); gated by site_config fclists_enabled (default on).

Companies (2026-07-17 tree-checkbox yokoten — see fclists.nav_options, thin copy of
fcbi/fcbi/consolidate.py's pattern): `companies` MultiSelectList wins over the legacy single `company`
Link. Bin carries no company column, so the resolved list is joined the same way the single `company`
filter always was — via the Warehouse.company lookup — now with an `["in", companies]` filter on
Warehouse instead of a single equality; the velocity sub-query (`_units_sold`, over Sales Invoice, which
DOES carry company) uses the same resolved list directly. No Cost Centre filter this wave — Bin/Item are
not cost-centre attributed; out of scope per the yokoten applicability table.
"""
import frappe
from frappe import _
from frappe.utils import flt, cint, add_days, nowdate

from fclists.nav_options import resolve_companies_filter


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not _enabled():
		return _columns(), []
	return _columns(), _data(filters)


def _enabled():
	# site_config capability gate — default ON. Data, not code (D-002).
	val = frappe.conf.get("fclists_enabled")
	return True if val is None else cint(val)


def _columns():
	return [
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 160},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 190},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 120},
		{"label": _("UOM"), "fieldname": "stock_uom", "fieldtype": "Link", "options": "UOM", "width": 70},
		{"label": _("On Hand"), "fieldname": "on_hand", "fieldtype": "Float", "width": 90},
		{"label": _("Valuation"), "fieldname": "valuation_rate", "fieldtype": "Currency", "width": 110},
		{"label": _("Sell Price"), "fieldname": "selling_rate", "fieldtype": "Currency", "width": 110},
		{"label": _("Margin"), "fieldname": "margin", "fieldtype": "Currency", "width": 100},
		{"label": _("Margin %"), "fieldname": "margin_pct", "fieldtype": "Percent", "width": 90},
		{"label": _("Reorder Level"), "fieldname": "reorder_level", "fieldtype": "Float", "width": 110},
		{"label": _("Units Sold"), "fieldname": "units_sold", "fieldtype": "Float", "width": 100},
	]


def _data(filters):
	# --- item master (drives the row set) ------------------------------------------------------------
	# permission-checked (get_list): role read-perm + User Permissions scope the item rows. Every
	# lookup below is keyed to these permitted item codes.
	item_filters = {"disabled": 0, "is_stock_item": 1}
	if filters.get("item_group"):
		item_filters["item_group"] = filters.item_group
	items = frappe.get_list(
		"Item",
		filters=item_filters,
		fields=["name", "item_name", "item_group", "stock_uom"],
		order_by="item_name asc",
	)
	if not items:
		return []
	item_codes = [i.name for i in items]

	# --- on-hand + valuation from Bin, aggregated per item in PYTHON ----------------------------------
	# get_all here is safe: rows are intersected against the permitted item codes from the get_list
	# above (on-hand is an ATTRIBUTE of already-permitted items). The item_code IN clause is only sent
	# to SQL when an item_group filter has actually NARROWED the set — with no narrowing filter the
	# permitted set is "every enabled stock item", and on a large catalog that IN list is a
	# multi-megabyte query; fetching Bin unfiltered and intersecting in Python is strictly cheaper.
	companies = resolve_companies_filter(filters.get("companies"), filters.get("company"))
	bin_filters = {}
	if filters.get("item_group"):
		bin_filters["item_code"] = ["in", item_codes]
	if filters.get("warehouse"):
		bin_filters["warehouse"] = filters.warehouse
	elif companies:
		# Bin has no company column — scope by the warehouses that belong to the resolved companies.
		allowed = [w.name for w in frappe.get_all(
			"Warehouse", filters={"company": ["in", companies]}, fields=["name"], order_by="name asc"
		)]
		if not allowed:
			return []
		bin_filters["warehouse"] = ["in", allowed]

	permitted = set(item_codes)
	bins = [
		b for b in frappe.get_all(
			"Bin",
			filters=bin_filters,
			fields=["item_code", "actual_qty", "valuation_rate", "stock_value"],
			order_by="item_code asc",
		)
		if b.item_code in permitted  # Python-side intersection — never widens beyond get_list's rows
	]

	on_hand = {}
	stock_value = {}
	for b in bins:
		on_hand[b.item_code] = flt(on_hand.get(b.item_code, 0)) + flt(b.actual_qty)
		stock_value[b.item_code] = flt(stock_value.get(b.item_code, 0)) + flt(b.stock_value)

	# --- reorder level: max over the Item Reorder child rows, in PYTHON -------------------------------
	# get_all here is safe: child rows of the permitted items only.
	reorder = {}
	for r in frappe.get_all(
		"Item Reorder",
		filters={"parent": ["in", item_codes], "parenttype": "Item"},
		fields=["parent", "warehouse_reorder_level"],
		order_by="parent asc",
	):
		lvl = flt(r.warehouse_reorder_level)
		if lvl > flt(reorder.get(r.parent, 0)):
			reorder[r.parent] = lvl

	# --- selling price: Item Price on the default selling price list ----------------------------------
	# get_all here is safe: the price is an ATTRIBUTE of already-permitted items (Item Price read is
	# natively Master-Manager-only; routing it through get_list would blank the board's core column
	# for the very Stock roles the Report doc admits).
	price_list = _selling_price_list(filters)
	selling = {}
	if price_list:
		for p in frappe.get_all(
			"Item Price",
			filters={"item_code": ["in", item_codes], "price_list": price_list, "selling": 1},
			fields=["item_code", "price_list_rate"],
			order_by="modified desc",
		):
			# first (freshest) wins; do not overwrite once set
			selling.setdefault(p.item_code, flt(p.price_list_rate))

	# --- velocity: units sold in the last N days from submitted Sales Invoice lines -------------------
	units_sold = _units_sold(filters, companies, item_codes)

	# --- assemble ------------------------------------------------------------------------------------
	# valuation per item = weighted (stock_value / on_hand) when qty > 0, else fall back to any bin rate.
	val_fallback = {}
	for b in bins:
		val_fallback.setdefault(b.item_code, flt(b.valuation_rate))

	rows = []
	for it in items:
		code = it.name
		qty = flt(on_hand.get(code, 0))
		if qty:
			valuation = flt(stock_value.get(code, 0)) / qty
		else:
			valuation = flt(val_fallback.get(code, 0))
		sell = flt(selling.get(code, 0))
		margin = sell - valuation
		margin_pct = (margin / valuation * 100.0) if valuation else 0.0
		rows.append({
			"item_code": code,
			"item_name": it.item_name,
			"item_group": it.item_group,
			"stock_uom": it.stock_uom,
			"on_hand": qty,
			"valuation_rate": valuation,
			"selling_rate": sell,
			"margin": margin,
			"margin_pct": flt(margin_pct, 2),
			"reorder_level": flt(reorder.get(code, 0)),
			"units_sold": flt(units_sold.get(code, 0)),
		})
	return rows


def _selling_price_list(filters):
	if filters.get("price_list"):
		return filters.price_list
	# Selling Settings default, else the first enabled selling price list (a NAME lookup for the
	# default — reference data, not row data — so get_all is fine here).
	pl = frappe.db.get_single_value("Selling Settings", "selling_price_list")
	if pl:
		return pl
	rows = frappe.get_all(
		"Price List",
		filters={"selling": 1, "enabled": 1},
		fields=["name"],
		order_by="name asc",
		limit=1,
	)
	return rows[0].name if rows else None


def _units_sold(filters, companies, item_codes):
	# Cross-module enrichment: the Report doc admits Stock roles, which natively lack Sales Invoice
	# read — degrade velocity to 0 for them rather than leak (or hard-error on) sales rows.
	if not frappe.has_permission("Sales Invoice"):
		return {}
	days = cint(filters.get("window_days")) or 30
	from_date = add_days(nowdate(), -days)
	si_filters = {"docstatus": 1, "posting_date": [">=", from_date], "is_return": 0}
	if companies:
		si_filters["company"] = ["in", companies]
	# permission-checked (get_list): role read-perm + User Permissions scope the invoice set; the
	# child-line get_all below is scoped to these permitted parents.
	invoices = frappe.get_list(
		"Sales Invoice", filters=si_filters, fields=["name"], order_by="posting_date desc"
	)
	if not invoices:
		return {}
	inv_names = [i.name for i in invoices]

	sold = {}
	line_filters = {"parent": ["in", inv_names], "item_code": ["in", item_codes]}
	for li in frappe.get_all(
		"Sales Invoice Item",
		filters=line_filters,
		fields=["item_code", "stock_qty", "qty"],
		order_by="parent asc",
	):
		q = flt(li.stock_qty) or flt(li.qty)
		sold[li.item_code] = flt(sold.get(li.item_code, 0)) + q
	return sold
