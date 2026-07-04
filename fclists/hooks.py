app_name = "fclists"
app_title = "FCLists"
app_publisher = "Flowcore"
app_description = "QuickBooks-POS-style transaction histories + dense computed lists for ERPNext"
app_email = "afyamart@gmail.com"
app_license = "MIT"

# Apps
# ------------------
# FCLists composes NATIVE ERPNext doctypes only (Item, Bin, Stock Ledger Entry, Batch, Sales Invoice,
# POS Invoice, Payment Entry, GL Entry, Account, Customer, Supplier). It depends on ERPNext and NOTHING
# else — never any Flowcore-family app (keep this list at exactly ["erpnext"]).
required_apps = ["erpnext"]

# Each item in the list will be shown as an app in the apps page.
# v16 route base is /desk/<workspace-slug> — never author /app/ URLs (flowcore-ui-standard §2.2).
add_to_apps_screen = [
	{
		"name": "fclists",
		"logo": "/assets/fclists/images/logo.svg",
		"title": "FCLists",
		"route": "/desk/fclists",
	}
]

# Includes in <head>
# ------------------

# The reusable loader primitive — defines frappe.provide("fclists") + fclists.extend_listview(...).
# Loaded on every desk page so every *_list.js can safely EXTEND native listview_settings (Finding A).
app_include_js = ["/assets/fclists/js/fclists_lib.js"]

# include js in doctype list views (Wave-1 doctypes only).
# Each of these files EXTENDS the native listview via fclists.extend_listview() — never a bare
# `frappe.listview_settings["X"] = {...}` reassignment (Frappe concatenates every app's list-js; a bare
# assignment would clobber ERPNext's own list config for the doctype). See fclists_lib.js. Finding A.
# The family lanes AUTHOR these files; this hook only DECLARES them.
# Wave-1 keys (Item/Batch/Sales Invoice/POS Invoice) + Wave-2 keys (Customer/Supplier/Purchase Invoice/
# Account). Every one of these files EXTENDS the native listview via fclists.extend_listview() — never a
# bare `frappe.listview_settings["X"] = {...}` reassignment (Finding A). See fclists_lib.js.
doctype_list_js = {
	# --- Wave-1 (authored) --------------------------------------------------------------------------------
	"Item": "public/js/item_list.js",
	"Batch": "public/js/batch_list.js",
	"Sales Invoice": "public/js/sales_invoice_list.js",
	"POS Invoice": "public/js/pos_invoice_list.js",
	# --- Wave-2 (family lanes AUTHOR these four files; this hook DECLARES them) ---------------------------
	"Customer": "public/js/customer_list.js",
	"Supplier": "public/js/supplier_list.js",
	"Purchase Invoice": "public/js/purchase_invoice_list.js",
	"Account": "public/js/account_list.js",
}

# Installation
# ------------
# No after_install seam is required (the reports reuse NATIVE roles, so there is nothing to seed). The
# after_migrate hook below calls a no-op-safe ensure() that leaves a documented seam for the future.
after_migrate = "fclists.setup.after_migrate"

# Fixtures
# --------
# Ship the desk shell (Workspace + Desktop Icon + the desk Number Cards) so `bench install-app` / `migrate`
# seeds them. These are additive and upgrade-safe. The Workspace lives in the module tree
# (fclists/fclists/workspace/); the Desktop Icon and the Number Cards are package-level standard fixtures.
#
# Dashboard, Dashboard Chart and Number Card are SHARED doctypes (every app defines its own), so each filter
# is scoped to OUR fixtures by NAME PREFIX ("FCLists"/"FClist") — never a bare {"dt": "Number Card"} (that
# would export/overwrite other apps' — or a client's — cards). BI is built on NATIVE frappe core doctypes
# (Dashboard / Dashboard Chart / Number Card): NO hard dependency on Frappe Insights or any BI app. Each card
# and chart counts/groups over NATIVE erpnext doctypes/reports only, with NO client-specific filters, so it is
# role-safe for every tenant (Finding B parity). Number Cards are additionally role-gated on their own `roles`
# table. The `like` filter exports both "FCLists …" and "FClist …" fixtures (report cards use the FClist
# report-name prefix; dashboards/charts use the FCLists app prefix).
#   Number Cards (report/count cards, role-gated):
#     FClist Items Below Reorder   — Count over the FClist Reorder report (Stock roles)
#     FClist Batches Expiring 30d  — Count of Batch expiring within 30 days (Stock roles)
#     FClist Overdue Invoices      — Count of submitted Sales Invoice past due with outstanding (Accounts roles)
#     FClist Total Sales MTD       — Sum of grand_total on submitted Sales Invoice this month (Accounts roles)
#     FClist Overdue AR            — Sum of outstanding on overdue submitted Sales Invoice (Accounts roles)
#   Dashboard Charts + Dashboard (BI lane authors the fixture rows under these name prefixes).
fixtures = [
	{"dt": "Desktop Icon", "filters": [["name", "=", "fclists"]]},
	{"dt": "Number Card", "filters": [["name", "like", "FClist %"]]},
	{"dt": "Dashboard Chart", "filters": [["name", "like", "FClist %"]]},
	{"dt": "Dashboard", "filters": [["name", "like", "FCLists%"]]},
	# The desk left-nav (Flowcore UI Standard: nav via Workspace Sidebar). Without this fixture the
	# desk auto-snapshots a sidebar from whatever the Workspace held on FIRST visit and never
	# regenerates it — a Wave-1 visitor would keep a 9-report sidebar forever (S033 bug).
	{"dt": "Workspace Sidebar", "filters": [["name", "=", "FCLists"]]},
]
