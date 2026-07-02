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

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "fclists",
		"logo": "/assets/fclists/images/logo.svg",
		"title": "FCLists",
		"route": "/app/fclists",
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
# The family lanes AUTHOR these four files; this hook only DECLARES them.
doctype_list_js = {
	"Item": "public/js/item_list.js",
	"Batch": "public/js/batch_list.js",
	"Sales Invoice": "public/js/sales_invoice_list.js",
	"POS Invoice": "public/js/pos_invoice_list.js",
}

# --- Wave-2 list-js (NOT declared yet — next wave adds these keys + authors the files) -----------------
# When Wave 2 lands, extend `doctype_list_js` above with (each file must use fclists.extend_listview()):
#   "Customer": "public/js/customer_list.js",
#   "Account":  "public/js/account_list.js",
#   "Supplier": "public/js/supplier_list.js",
# ------------------------------------------------------------------------------------------------------

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
# Number Card is a SHARED doctype (every app defines its own), so the filter is scoped to OUR three cards by
# name — never a bare {"dt": "Number Card"} (that would export/overwrite other apps' cards). Each card counts
# over NATIVE erpnext doctypes/reports only and is role-gated on its own `roles` table (Finding B parity):
#   FClist Items Below Reorder   — Count over the FClist Reorder report (Stock roles)
#   FClist Batches Expiring 30d  — Count of Batch expiring within 30 days (Stock roles)
#   FClist Overdue Invoices      — Count of submitted Sales Invoice past due with outstanding (Accounts roles)
fixtures = [
	{"dt": "Desktop Icon", "filters": [["name", "=", "fclists"]]},
	{
		"dt": "Number Card",
		"filters": [
			[
				"name",
				"in",
				[
					"FClist Items Below Reorder",
					"FClist Batches Expiring 30d",
					"FClist Overdue Invoices",
				],
			]
		],
	},
]
