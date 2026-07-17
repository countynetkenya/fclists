"""FClist Account — dense Chart-of-Accounts board with live balances (QBO "Chart of Accounts" density parity).

One glance at the whole COA: account name, account_type, root_type, whether it is a group, and the LIVE
BALANCE as of a date (summed from GL Entry per company, in Python). The native Account tree cannot show a
balance column — it is derived from the ledger against an as-of date — so this Script Report is the native
tool.

Security (Finding B): role-gated on its Report doc (native Accounts roles + System Manager) — never
world-readable. The row-driving Account query runs through frappe.get_list → read permission is checked
and User Permissions scope the rows (a user permitted to Company A never sees Company B's accounts); the
balance aggregation then reads GL only for those already-permitted accounts. No raw SQL, so no
build_match_conditions needed.

v16-safe: balances are summed in PYTHON (frappe.get_all rejects "sum(x) as y" field strings); every query
passes an explicit order_by (tree order via lft, then name). Sector-neutral (no client literal).

Companies / Cost Centre (2026-07-17 tree-checkbox yokoten — see fclists.nav_options, thin copy of
fcbi/fcbi/consolidate.py's pattern): `companies` MultiSelectList wins over the legacy single `company`
Link, scoping BOTH which accounts are listed (Account.company) and the GL Entry balance sum
(GL Entry.company). `cost_center` has no meaning on the Account master itself (an account is not tied to
a cost centre) — it instead scopes the LIVE BALANCE computation: passing one or more Cost Centres restricts
the GL Entry sum that produces each row's `balance` to those cost centres, while the account ROWS shown stay
governed by `companies` alone. This is a deliberate, clean query-shape fit (GL Entry already carries
cost_center; no join/rewrite needed) — same idiom as fclist_gl.py's leaf-table filter.
"""
import frappe
from frappe import _
from frappe.utils import flt, nowdate

from fclists.nav_options import resolve_companies_filter, resolve_cost_centre_filter


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return _columns(), _data(filters)


def _columns():
	return [
		{"label": _("Account"), "fieldname": "name", "fieldtype": "Link", "options": "Account", "width": 260},
		{"label": _("Account Name"), "fieldname": "account_name", "fieldtype": "Data", "width": 200},
		{"label": _("Type"), "fieldname": "account_type", "fieldtype": "Data", "width": 130},
		{"label": _("Root Type"), "fieldname": "root_type", "fieldtype": "Data", "width": 110},
		{"label": _("Is Group"), "fieldname": "is_group", "fieldtype": "Data", "width": 80},
		{"label": _("Currency"), "fieldname": "account_currency", "fieldtype": "Link", "options": "Currency", "width": 90},
		{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "options": "account_currency", "width": 150},
	]


def _data(filters):
	acc_filters = {}
	companies = resolve_companies_filter(filters.get("companies"), filters.get("company"))
	if companies:
		acc_filters["company"] = ["in", companies]
	if filters.get("root_type"):
		acc_filters["root_type"] = filters.root_type

	# permission-checked (get_list): role read-perm + User Permissions scope the account rows.
	accounts = frappe.get_list(
		"Account",
		filters=acc_filters,
		fields=[
			"name", "account_name", "account_type", "root_type",
			"is_group", "account_currency", "lft",
		],
		order_by="lft asc, name asc",
	)
	if not accounts:
		return []

	balances = _balances(filters, companies, [a.name for a in accounts])

	rows = []
	for a in accounts:
		rows.append({
			"name": a.name,
			"account_name": a.account_name,
			"account_type": a.account_type,
			"root_type": a.root_type,
			"is_group": _("Yes") if a.is_group else _("No"),
			"account_currency": a.account_currency,
			"balance": flt(balances.get(a.name, 0)),
		})
	return rows


def _balances(filters, companies, account_names):
	"""Balance per account = SUM(debit) - SUM(credit) from GL Entry, as-of date, summed in PYTHON."""
	gle_filters = {"account": ["in", account_names], "is_cancelled": 0}
	if companies:
		gle_filters["company"] = ["in", companies]
	cost_centers = resolve_cost_centre_filter(filters.get("cost_center"))
	if cost_centers:
		gle_filters["cost_center"] = ["in", cost_centers]
	as_of = filters.get("as_of_date") or nowdate()
	gle_filters["posting_date"] = ["<=", as_of]

	balances = {}
	# get_all here is safe: scoped to account names that came from the permission-checked get_list
	# above (Account is company-specific, so permitted accounts ⇒ permitted companies' GL only).
	for gle in frappe.get_all(
		"GL Entry",
		filters=gle_filters,
		fields=["account", "debit", "credit"],
		order_by="account asc",
	):
		balances[gle.account] = flt(balances.get(gle.account, 0)) + flt(gle.debit) - flt(gle.credit)
	return balances
