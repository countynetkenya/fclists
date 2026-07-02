"""Page controller for the FCLists user guide (login-gated web page).

Gates the guide to the roles that can actually READ an FCLists report, so what a user reads matches what
they can open. Those are exactly the NATIVE ERPNext roles populated on the reports' ``roles`` tables (see
each report JSON): the Stock roles (Stock User / Stock Manager) for the stock boards and the Accounts roles
(Accounts User / Accounts Manager) for the transaction histories, plus System Manager.

Behaviour:
- **Guest** → ``frappe.PermissionError`` → Frappe redirects to ``/login`` (then back here after sign-in).
- **Signed-in without any report-reading role** → ``frappe.PermissionError`` → 403.
- **Signed-in with a report-reading role** → the page renders.

Sector-neutral (no client literal); no dependency beyond ERPNext. Read-only page — no writes, no commit.
"""

import frappe
from frappe import _

# The union of roles that gate at least one FClist report (see the report JSONs). A user who holds ANY of
# these can open at least one FClist report, so they may read the guide. Kept in sync with the reports by
# hand (there are nine of them); if a wave adds a report gated on a new native role, add it here too.
ALLOWED_ROLES = {
	"System Manager",
	"Stock Manager",
	"Stock User",
	"Accounts Manager",
	"Accounts User",
}


def get_context(context):
	# Guests have only the "Guest" role → the intersection is empty → PermissionError → Frappe sends them
	# to /login and returns them here after sign-in. Signed-in users lacking every report role get a 403.
	if frappe.session.user == "Guest" or not (ALLOWED_ROLES & set(frappe.get_roles())):
		raise frappe.PermissionError(_("Please sign in with a Stock or Accounts role to view this guide."))

	context.no_cache = 1
	context.title = "FCLists — User Guide"
