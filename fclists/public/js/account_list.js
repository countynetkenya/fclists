// FClist — Account (Chart of Accounts) dense list.
// Chain a group/root-type indicator onto the native Account list and add a jump to the QuickBooks-style
// "FClist Account" Script Report (COA density + live balances). EXTEND, never replace: we call
// fclists.extend_listview() (defined in fclists_lib.js) so ERPNext's own list config for Account — its
// indicators, buttons, add_fields — is preserved and merely augmented. A bare
// frappe.listview_settings["Account"] = {...} would clobber it (Frappe concatenates every app's list-js).
// Finding A.
(function () {
	"use strict";

	fclists.extend_listview("Account", {
		// Fetch what our indicator needs (concatenated onto native add_fields, never replacing them).
		add_fields: ["is_group", "root_type", "account_type"],

		get_indicator: function (doc) {
			// Group (header) accounts read differently from postable leaves. Runs FIRST; returning
			// undefined falls through to the native/prior get_indicator (chained by the helper).
			if (cint(doc.is_group)) {
				return [__("Group"), "gray", "is_group,=,1"];
			}
			if (doc.root_type) {
				return [__(doc.root_type), "blue", "root_type,=," + doc.root_type];
			}
			// else: fall through to native.
		},

		onload: function (listview) {
			// Native/prior onload runs first (chained by the helper), then this inner button.
			listview.page.add_inner_button(__("Balances"), function () {
				frappe.set_route("query-report", "FClist Account");
			});
		},
	});
})();
