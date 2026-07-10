"""FClist Held Documents — parked NATIVE drafts, all in one glance (QB-POS "Held" parity).

One row per DRAFT (docstatus 0) Stock Entry / Stock Reconciliation / Purchase Receipt: type, name, owner,
last-modified, company. A till parks an in-progress quantity adjustment, transfer, cost adjustment, or
receiving voucher as a native draft instead of posting it half-finished; this Script Report is the single
"what's parked, by whom, since when" board across all three draft-producing doctypes — no shadow "held"
table, no fcduka reference (clean-room, erpnext-only dep, D-048 law).

Security (Finding B): role-gated on its Report doc (Stock User / Accounts Manager / System Manager) —
never world-readable. Each doctype's rows are read through frappe.get_list → read permission is checked
and User Permissions scope the rows per doctype (a user permitted to Company A never sees Company B's
drafts). No raw SQL, so no build_match_conditions needed.

v16-safe: explicit order_by on every read; a limit per doctype so an unfiltered open is bounded;
read-only. Sector-neutral; gated by site_config ``fclists_enabled``.
"""
import frappe
from frappe import _
from frappe.utils import cint

# The three native doctypes a till can park a draft in (docstatus 0 = held, not yet posted). Purely
# native erpnext doctypes — no fcduka import (fclists LAW).
_HELD_DOCTYPES = ("Stock Entry", "Stock Reconciliation", "Purchase Receipt")


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
		{"label": _("Type"), "fieldname": "type", "fieldtype": "Data", "width": 160},
		{"label": _("Name"), "fieldname": "name", "fieldtype": "Dynamic Link", "options": "type", "width": 170},
		{"label": _("Owner"), "fieldname": "owner", "fieldtype": "Link", "options": "User", "width": 180},
		{"label": _("Modified"), "fieldname": "modified", "fieldtype": "Datetime", "width": 160},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 160},
	]


def _data(filters):
	limit = cint(filters.get("limit")) or 200
	rows = []
	for dt in _HELD_DOCTYPES:
		dt_filters = {"docstatus": 0}
		if filters.get("company"):
			dt_filters["company"] = filters.company
		if filters.get("owner"):
			dt_filters["owner"] = filters.owner

		# permission-checked (get_list): role read-perm + User Permissions scope the rows, per doctype.
		recs = frappe.get_list(
			dt,
			filters=dt_filters,
			fields=["name", "owner", "modified", "company"],
			order_by="modified desc",
			limit=limit,
		)
		for r in recs:
			rows.append({
				"type": dt,
				"name": r.name,
				"owner": r.owner,
				"modified": r.modified,
				"company": r.company,
			})

	rows.sort(key=lambda r: r["modified"] or "", reverse=True)
	return rows
