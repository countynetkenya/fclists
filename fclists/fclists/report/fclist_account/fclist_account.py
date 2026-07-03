"""FClist Account — dense Chart-of-Accounts board with live balances (QBO "Chart of Accounts" density parity).

One glance at the whole COA: account name, account_type, root_type, whether it is a group, and the LIVE
BALANCE as of a date (summed from GL Entry per company, in Python). The native Account tree cannot show a
balance column — it is derived from the ledger against an as-of date — so this Script Report is the native
tool.

Security (Finding B): ORM-only (frappe.get_all) → User Permissions enforced automatically. No raw SQL, so
no build_match_conditions needed. The report is role-gated on its Report doc (native Accounts roles + System
Manager) — never world-readable.

v16-safe: balances are summed in PYTHON (frappe.get_all rejects "sum(x) as y" field strings); every query
passes an explicit order_by (tree order via lft, then name). Sector-neutral (no client literal).
"""
import frappe
from frappe import _
from frappe.utils import flt, nowdate


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
	if filters.get("company"):
		acc_filters["company"] = filters.company
	if filters.get("root_type"):
		acc_filters["root_type"] = filters.root_type

	accounts = frappe.get_all(
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

	balances = _balances(filters, [a.name for a in accounts])

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


def _balances(filters, account_names):
	"""Balance per account = SUM(debit) - SUM(credit) from GL Entry, as-of date, summed in PYTHON."""
	gle_filters = {"account": ["in", account_names], "is_cancelled": 0}
	if filters.get("company"):
		gle_filters["company"] = filters.company
	as_of = filters.get("as_of_date") or nowdate()
	gle_filters["posting_date"] = ["<=", as_of]

	balances = {}
	for gle in frappe.get_all(
		"GL Entry",
		filters=gle_filters,
		fields=["account", "debit", "credit"],
		order_by="account asc",
	):
		balances[gle.account] = flt(balances.get(gle.account, 0)) + flt(gle.debit) - flt(gle.credit)
	return balances
