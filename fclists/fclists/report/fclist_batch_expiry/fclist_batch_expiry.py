"""FClist Batch Expiry — FEFO board for batches carrying an expiry_date.

Per batch: batch_no, item, expiry_date, days_to_expiry, qty remaining (live from tabStock Ledger Entry by
batch — Bin is per-item-per-warehouse, not per-batch), and a STATUS flag (Expired / Expiring<=Nd / OK).
GENERIC — no sector literal (works for any perishable inventory, not just one vertical).

Security (Finding B): role-gated on the Report doc. The row-driving Batch query runs through
frappe.get_list → read permission is checked; the item-name and qty lookups then read only for those
already-permitted batches. NOTE the honest scope: User Permissions restrict rows only for doctypes
that CARRY the restricted link field — Batch has no company field, so a Company User Permission does
NOT partition this board (it is role-gated + read-checked, not company-scoped; the company filter
here narrows the SLE qty sum only).
v16-safe: batch-qty sums done in PYTHON over SLE rows; explicit order_by (FEFO = expiry_date asc). Sector-
neutral; gated by site_config fclists_enabled.
"""
import frappe
from frappe import _
from frappe.utils import flt, cint, date_diff, nowdate


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
		{"label": _("Batch"), "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 170},
		{"label": _("Item"), "fieldname": "item", "fieldtype": "Link", "options": "Item", "width": 160},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Expiry Date"), "fieldname": "expiry_date", "fieldtype": "Date", "width": 110},
		{"label": _("Days to Expiry"), "fieldname": "days_to_expiry", "fieldtype": "Int", "width": 120},
		{"label": _("Qty Remaining"), "fieldname": "qty_remaining", "fieldtype": "Float", "width": 120},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
	]


def _data(filters):
	warn_days = cint(filters.get("warn_days")) or 30

	# --- batches carrying an expiry date (drives the row set) ----------------------------------------
	batch_filters = {"expiry_date": ["is", "set"], "disabled": 0}
	if filters.get("item"):
		batch_filters["item"] = filters.item
	# permission-checked (get_list): role read-perm. Batch carries no company field, so a Company
	# User Permission does not scope these rows — role-gated + read-checked only (see module docstring).
	batches = frappe.get_list(
		"Batch",
		filters=batch_filters,
		fields=["name", "item", "expiry_date"],
		order_by="expiry_date asc",
	)
	if not batches:
		return []

	# --- item-group filter + item names (ORM lookup) -------------------------------------------------
	# get_all here is safe: scoped to the items of batches that came from the permission-checked
	# get_list above (attributes of already-permitted rows, not new rows).
	item_codes = list({b.item for b in batches})
	item_master_filters = {"name": ["in", item_codes]}
	if filters.get("item_group"):
		item_master_filters["item_group"] = filters.item_group
	items = {
		i.name: i
		for i in frappe.get_all(
			"Item",
			filters=item_master_filters,
			fields=["name", "item_name"],
			order_by="name asc",
		)
	}

	batch_names = [b.name for b in batches if b.item in items]
	if not batch_names:
		return []

	# --- qty remaining per batch = sum of SLE actual_qty, in PYTHON ----------------------------------
	# get_all here is safe: scoped to batch names from the permission-checked get_list above.
	sle_filters = {"batch_no": ["in", batch_names], "is_cancelled": 0}
	if filters.get("warehouse"):
		sle_filters["warehouse"] = filters.warehouse
	elif filters.get("company"):
		sle_filters["company"] = filters.company

	qty = {}
	for s in frappe.get_all(
		"Stock Ledger Entry",
		filters=sle_filters,
		fields=["batch_no", "actual_qty"],
		order_by="batch_no asc",
	):
		qty[s.batch_no] = flt(qty.get(s.batch_no, 0)) + flt(s.actual_qty)

	today = nowdate()
	status_filter = filters.get("status")
	rows = []
	for b in batches:
		if b.name not in batch_names:
			continue
		remaining = flt(qty.get(b.name, 0))
		if remaining <= 0 and not cint(filters.get("show_depleted")):
			continue
		dte = date_diff(b.expiry_date, today)
		if dte < 0:
			status = "Expired"
		elif dte <= warn_days:
			status = "Expiring"
		else:
			status = "OK"
		if status_filter and status != status_filter:
			continue
		it = items.get(b.item) or frappe._dict()
		rows.append({
			"batch_no": b.name,
			"item": b.item,
			"item_name": it.get("item_name"),
			"expiry_date": b.expiry_date,
			"days_to_expiry": dte,
			"qty_remaining": remaining,
			"status": status,
		})
	# FEFO order: soonest expiry first (already sorted, but keep it explicit and stable).
	rows.sort(key=lambda r: (r["days_to_expiry"], r["batch_no"]))
	return rows
