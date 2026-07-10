"""FClist Duplicate Items — normalized-name clustering over enabled Items (D-070 hygiene).

Jason's gemba: beef/Beef duplicated a prior group item list — a cashier free-typing an item name at the
till (via Add-New) can silently mint a second Item for something that already exists, split under a
slightly different spelling, case, or punctuation ("Maize 6213 2 kg" vs "Maize 6213 2 kg +T"). This Script
Report is the single board that surfaces every cluster of enabled Items whose NAME collapses to the same
normalized key, so a manager can spot and merge/retire the duplicates before they split stock, pricing and
sales history across two item_codes.

One row per CLUSTER (normalized key shared by 2+ enabled Items): normalized_key, count, item_codes,
item_names, item_groups. No shadow table, no cross-app import (clean-room, erpnext-only dep, D-048 law) — the
normalizer below is fclists' OWN copy (the POS Add-New guard carries an identical small pure
fn; clean-room beats DRY here, noted in both).

Security (Finding B): role-gated on its Report doc (Stock User / Stock Manager / Accounts Manager / System
Manager) — never world-readable. Rows are read through frappe.get_list → read permission is checked and
User Permissions scope the Items returned to whatever the caller may see.

v16-safe: explicit order_by; read-only; no raw SQL. Sector-neutral; gated by site_config
``fclists_enabled`` (mirrors FClist Held Documents).
"""
import re

import frappe
from frappe import _
from frappe.utils import cint

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def _normalize(name):
	# casefold + strip punctuation + collapse whitespace + trim — the working key for "same item, different
	# spelling/case/punctuation". Deliberately a SMALL pure fn, owned here (clean-room LAW: no cross-app import).
	s = _PUNCT_RE.sub(" ", (name or "").casefold())
	return _SPACE_RE.sub(" ", s).strip()


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
		{"label": _("Normalized Name"), "fieldname": "normalized_key", "fieldtype": "Data", "width": 220},
		{"label": _("Count"), "fieldname": "count", "fieldtype": "Int", "width": 70},
		{"label": _("Item Codes"), "fieldname": "item_codes", "fieldtype": "Data", "width": 220},
		{"label": _("Item Names"), "fieldname": "item_names", "fieldtype": "Data", "width": 260},
		{"label": _("Item Groups"), "fieldname": "item_groups", "fieldtype": "Data", "width": 200},
	]


def _data(filters):
	item_group = filters.get("item_group")
	dt_filters = {"disabled": 0}
	if item_group:
		dt_filters["item_group"] = item_group

	# permission-checked (get_list): role read-perm + User Permissions scope the Items returned.
	items = frappe.get_list(
		"Item",
		filters=dt_filters,
		fields=["item_code", "item_name", "item_group"],
		order_by="item_code asc",
		limit_page_length=0,
	)

	clusters = {}
	for it in items:
		key = _normalize(it.item_name)
		if not key:
			continue
		clusters.setdefault(key, []).append(it)

	rows = []
	for key, group in clusters.items():
		if len(group) < 2:
			continue
		rows.append({
			"normalized_key": key,
			"count": len(group),
			"item_codes": ", ".join(g.item_code for g in group),
			"item_names": ", ".join(g.item_name for g in group),
			"item_groups": ", ".join(sorted({g.item_group for g in group if g.item_group})),
		})

	rows.sort(key=lambda r: (-r["count"], r["normalized_key"]))
	return rows
