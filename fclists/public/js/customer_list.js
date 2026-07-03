// FClist — Customer dense list (AR lane).
// Chain an AR/past-due indicator onto the native Customer list and add a jump to the QuickBooks-style
// AR board Script Report. EXTEND, never replace: we call fclists.extend_listview() (defined in
// fclists_lib.js) so ERPNext's own list config for Customer — its indicators, buttons, add_fields — is
// preserved and merely augmented. A bare `frappe.listview_settings["Customer"] = {...}` would clobber
// it (Frappe concatenates every app's list-js). Finding A.
(function () {
	"use strict";

	fclists.extend_listview("Customer", {
		// Native Customer list already knows disabled/customer_group; nothing extra needed for the button.
		add_fields: ["disabled"],

		get_indicator: function (doc) {
			// Disabled customers: gray. Runs FIRST; returning undefined falls through to native/prior.
			if (cint(doc.disabled)) {
				return [__("Disabled"), "gray", "disabled,=,1"];
			}
			// else: fall through to native (Enabled, etc.). Outstanding AR is per-invoice, not a Customer
			// field, so the money view lives in the "AR Board" report reached by the button below.
		},

		onload: function (listview) {
			// Native/prior onload runs first (chained by the helper), then this inner button.
			listview.page.add_inner_button(__("AR Board"), function () {
				frappe.set_route("query-report", "FClist Customer Balance");
			});
		},
	});
})();
