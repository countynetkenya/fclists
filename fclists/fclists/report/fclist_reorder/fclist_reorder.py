"""FClist Reorder — items whose on-hand has fallen to or below their reorder level.

Per item: item, item_group, on-hand (sum tabBin.actual_qty), reorder_level (max over Item Reorder rows),
shortfall (reorder_level - on_hand) and default_supplier. The reorder decision needs live Bin qty joined
to the Item Reorder child rows — a plain list cannot compute it, so this is the native Script Report.

Security (Finding B): role-gated on the Report doc. The row-driving Item query runs through
frappe.get_list → read permission is checked and User Permissions scope the rows; reorder-level and
on-hand lookups are keyed to those already-permitted items only.
v16-safe: sums in PYTHON; explicit order_by. Sector-neutral; gated by site_config fclists_enabled.
"""
import frappe
from frappe import _
from frappe.utils import flt, cint


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not _enabled():
		return _columns(), []
	return _columns(), _data(filters)


def _enabled():
	val = frappe.conf.get("fclists_enabled")
	return True if val is None else cint(val)


def _columns():
	return [
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 170},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("Item Group"), "fieldname": "item_group", "fieldtype": "Link", "options": "Item Group", "width": 130},
		{"label": _("On Hand"), "fieldname": "on_hand", "fieldtype": "Float", "width": 100},
		{"label": _("Reorder Level"), "fieldname": "reorder_level", "fieldtype": "Float", "width": 120},
		{"label": _("Shortfall"), "fieldname": "shortfall", "fieldtype": "Float", "width": 100},
		{"label": _("Default Supplier"), "fieldname": "default_supplier", "fieldtype": "Link", "options": "Supplier", "width": 180},
		# constant 1 per row: Number Cards over Script Reports only support Sum/Average/Min/Max
		# (frappe report_utils.get_result_of_fn has no Count), so the workspace card counts rows
		# by summing this flag.
		{"label": _("Below Reorder?"), "fieldname": "below_reorder", "fieldtype": "Int", "width": 90},
	]


def _data(filters):
	# --- reorder levels: max per item over Item Reorder child rows (PYTHON) ---------------------------
	# get_all here only harvests CANDIDATE levels; a row is emitted below only for items that survive
	# the permission-checked get_list on Item (so no unpermitted item ever reaches the board).
	reorder_filters = {"parenttype": "Item", "warehouse_reorder_level": [">", 0]}
	if filters.get("warehouse"):
		reorder_filters["warehouse"] = filters.warehouse
	reorder = {}
	for r in frappe.get_all(
		"Item Reorder",
		filters=reorder_filters,
		fields=["parent", "warehouse_reorder_level"],
		order_by="parent asc",
	):
		lvl = flt(r.warehouse_reorder_level)
		if lvl > flt(reorder.get(r.parent, 0)):
			reorder[r.parent] = lvl
	if not reorder:
		return []
	item_codes = list(reorder.keys())

	# --- item master (restrict to codes that have a reorder level; apply group filter) ---------------
	item_filters = {"name": ["in", item_codes], "disabled": 0}
	if filters.get("item_group"):
		item_filters["item_group"] = filters.item_group
	# permission-checked (get_list): role read-perm + User Permissions scope the item rows.
	items = {
		i.name: i
		for i in frappe.get_list(
			"Item",
			filters=item_filters,
			fields=["name", "item_name", "item_group", "default_supplier"],
			order_by="item_name asc",
		)
	}
	if not items:
		return []

	# --- on-hand from Bin, aggregated per item in PYTHON ---------------------------------------------
	# get_all here is safe: scoped to the permitted item codes from the get_list above.
	bin_filters = {"item_code": ["in", list(items.keys())]}
	if filters.get("warehouse"):
		bin_filters["warehouse"] = filters.warehouse
	elif filters.get("company"):
		allowed = [w.name for w in frappe.get_all(
			"Warehouse", filters={"company": filters.company}, fields=["name"], order_by="name asc"
		)]
		if not allowed:
			return []
		bin_filters["warehouse"] = ["in", allowed]

	on_hand = {}
	for b in frappe.get_all(
		"Bin",
		filters=bin_filters,
		fields=["item_code", "actual_qty"],
		order_by="item_code asc",
	):
		on_hand[b.item_code] = flt(on_hand.get(b.item_code, 0)) + flt(b.actual_qty)

	# --- keep only items at/below reorder level ------------------------------------------------------
	rows = []
	for code, it in items.items():
		qty = flt(on_hand.get(code, 0))
		lvl = flt(reorder.get(code, 0))
		if qty <= lvl:
			rows.append({
				"item_code": code,
				"item_name": it.item_name,
				"item_group": it.item_group,
				"on_hand": qty,
				"reorder_level": lvl,
				"shortfall": lvl - qty,
				"default_supplier": it.default_supplier,
				"below_reorder": 1,
			})
	# most-urgent first (largest shortfall), stable tie-break by item.
	rows.sort(key=lambda r: (-r["shortfall"], r["item_code"]))
	return rows
