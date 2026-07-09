"""FClist Cost Adjustment — the line-level stock REVALUATION register (QB-POS "Cost Adjustment" parity).

One row per VALUATION-only Stock Reconciliation line: posting date, the reconciliation (link), company,
item, warehouse, the OLD valuation rate (``current_valuation_rate``), the NEW valuation rate
(``valuation_rate``), the stock VALUE moved, and the audit reason. This is the VALUATION sibling of the
quantity-count history: a cost adjustment (fcduka Inc-D) revalues stock WITHOUT changing quantity, so the
native Stock Reconciliation carries a row whose qty is unchanged and whose valuation_rate is rewritten —
only the stock VALUE and the Stock Adjustment Account GL move (D-003). This Script Report is the "what was
revalued, from what to what, worth how much, and why" board a manager reads without opening each
reconciliation one by one.

ISOLATING VALUATION reconciliations from QTY counts (the crux): a till count (count.py) and a cost
adjustment (cost_adjust.py) BOTH compose a Stock Reconciliation with ``purpose = "Stock Reconciliation"`` —
purpose alone cannot tell them apart. The discriminator is at the LINE level: a count row keeps the item's
current rate (``valuation_rate == current_valuation_rate``, only the qty moves), whereas a valuation
adjustment row rewrites the rate (``valuation_rate != current_valuation_rate``). So this report keeps ONLY
the rows that carry a genuine valuation change — a pure qty-count line is dropped, and a mixed
reconciliation surfaces only its revalued lines. No custom field and no fcduka import: the isolation is
pure native-field arithmetic, so this stays clean-room (erpnext-only) and reports a desk-authored
valuation SR just as faithfully as a till-authored one.

REASON: the cost_adjust.py endpoint stamps the audit note into the native ``remarks`` field (no custom
field — S059), per item as ``[<item>: <reason>]`` alongside a document-level note and an internal
``[fcduka_key:...]`` idempotency marker. This report surfaces the per-item reason when that marker is
present, else the document remarks with the internal key marker stripped — a best-effort read of a NATIVE
field (no format dependency, no import), so a plain desk SR simply shows its own remarks.

Security (Finding B + S034b): this is a COST report — every value column is valuation, so it is role-gated
on its Report doc to MANAGER/accounts roles only (Stock Manager / Accounts Manager / System Manager);
unlike the receiving list it deliberately EXCLUDES plain Stock User, so a bare cashier cannot even open it
(the S034b "a non-cost role sees no valuation" gate, enforced at the Report-role wall). The row-driving
reconciliation query runs through ``frappe.get_list`` → read permission is checked and User Permissions
scope the rows (a user permitted to Company A never sees Company B's revaluations); the item child rows are
read ONLY for those already-permitted reconciliations (scoped by ``parent in <permitted names>``). No raw
SQL, so no build_match_conditions needed.

v16-safe: explicit order_by on every read; a window_days default so an unfiltered open is bounded;
read-only. Sector-neutral; gated by site_config ``fclists_enabled``. Stock Reconciliation is a NATIVE
erpnext doctype, so this report lives in clean-room fclists (erpnext-only dep, no fcduka import).
"""
import re

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, nowdate

# The internal idempotency marker cost_adjust.py stamps into remarks — audit NOISE, stripped from display.
_KEY_MARKER_RE = re.compile(r"\s*\[fcduka_key:[^\]]*\]")

# A valuation change smaller than this (in the price currency) is treated as "no revaluation" — guards
# against float dust so a pure qty count never leaks in on a sub-cent rate wobble.
_RATE_EPS = 1e-6


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
		{"label": _("Posting Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
		{"label": _("Reconciliation"), "fieldname": "stock_reconciliation", "fieldtype": "Link", "options": "Stock Reconciliation", "width": 180},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 160},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 180},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 160},
		{"label": _("Old Valuation"), "fieldname": "old_valuation", "fieldtype": "Currency", "width": 120},
		{"label": _("New Valuation"), "fieldname": "new_valuation", "fieldtype": "Currency", "width": 120},
		{"label": _("Value Difference"), "fieldname": "value_difference", "fieldtype": "Currency", "width": 130},
		{"label": _("Reason"), "fieldname": "reason", "fieldtype": "Small Text", "width": 280},
	]


def _reason_for(remarks, item_code):
	"""Best-effort read of the audit reason from the NATIVE remarks (cost_adjust.py stamps ``[<item>:
	<reason>]`` per line + an internal ``[fcduka_key:...]`` marker). Return the per-item reason when its
	marker is present; else the document remarks with the internal key marker stripped. No format
	dependency: a plain desk SR (no markers) simply shows its own remarks."""
	if not remarks:
		return ""
	# Per-item marker: ``[<item_code>: <reason>]`` (item_code re.escaped; non-greedy to the first ]).
	m = re.search(r"\[" + re.escape(item_code) + r":\s*(.*?)\]", remarks)
	if m:
		return m.group(1).strip()
	# Fallback: the whole remarks, minus the internal idempotency marker (noise, not audit).
	return _KEY_MARKER_RE.sub("", remarks).strip()


def _data(filters):
	days = cint(filters.get("window_days")) or 30
	from_date = filters.get("from_date") or add_days(nowdate(), -days)
	to_date = filters.get("to_date") or nowdate()

	sr_filters = {
		"docstatus": 1,
		"posting_date": ["between", [from_date, to_date]],
	}
	if filters.get("company"):
		sr_filters["company"] = filters.company

	# permission-checked (get_list): role read-perm + User Permissions scope the reconciliation rows.
	recons = frappe.get_list(
		"Stock Reconciliation",
		filters=sr_filters,
		fields=["name", "posting_date", "company", "remarks"],
		order_by="posting_date desc, name desc",
	)
	if not recons:
		return []
	header = {r.name: r for r in recons}

	# get_all below is safe: child rows are scoped to the parents from the permission-checked get_list above
	# (a user who cannot read the reconciliation never reaches its lines). Explicit order_by (v16). Select
	# only native rate/qty fields so the valuation-vs-qty isolation is pure arithmetic (clean-room).
	item_filters = {"parenttype": "Stock Reconciliation", "parent": ["in", list(header)], "docstatus": 1}
	if filters.get("item"):
		item_filters["item_code"] = filters.item
	lines = frappe.get_all(
		"Stock Reconciliation Item",
		filters=item_filters,
		fields=[
			"parent", "item_code", "warehouse",
			"qty", "current_qty", "valuation_rate", "current_valuation_rate",
		],
		order_by="parent asc, idx asc",
		parent_doctype="Stock Reconciliation",
	)

	rows = []
	for ln in lines:
		old_val = flt(ln.current_valuation_rate)
		new_val = flt(ln.valuation_rate)
		# ISOLATE valuation lines: keep ONLY rows whose rate actually changed. A pure qty-count line
		# (valuation_rate == current_valuation_rate) is dropped — this is a revaluation register.
		if abs(new_val - old_val) < _RATE_EPS:
			continue
		h = header.get(ln.parent)
		if not h:
			continue
		# Stock VALUE moved: the new-basis value minus the old-basis value. For a valuation-only line the
		# qty is unchanged, so this reduces to qty x (new - old); computed from native fields directly so
		# there is no dependency on the stored amount_difference column.
		value_diff = flt(new_val * flt(ln.qty) - old_val * flt(ln.current_qty), 2)
		rows.append({
			"posting_date": h.posting_date,
			"stock_reconciliation": ln.parent,
			"company": h.company,
			"item_code": ln.item_code,
			"warehouse": ln.warehouse,
			"old_valuation": old_val,
			"new_valuation": new_val,
			"value_difference": value_diff,
			"reason": _reason_for(h.remarks, ln.item_code),
		})
	return rows
