// FClist — Supplier dense list (AP lane).
// Chain an AP indicator onto the native Supplier list and add a jump to the QuickBooks-style AP board
// Script Report. EXTEND, never replace: we call fclists.extend_listview() (defined in fclists_lib.js)
// so ERPNext's own list config for Supplier — its indicators, buttons, add_fields — is preserved and
// merely augmented. A bare `frappe.listview_settings["Supplier"] = {...}` would clobber it (Frappe
// concatenates every app's list-js). Finding A.
(function () {
	"use strict";

	fclists.extend_listview("Supplier", {
		add_fields: ["disabled", "on_hold"],

		get_indicator: function (doc) {
			// On-hold suppliers: red (payments blocked). Runs FIRST; undefined falls through to native.
			if (cint(doc.on_hold)) {
				return [__("On Hold"), "red", "on_hold,=,1"];
			}
			if (cint(doc.disabled)) {
				return [__("Disabled"), "gray", "disabled,=,1"];
			}
			// else: fall through to native. Outstanding AP is per-invoice, surfaced in the AP Board report.
		},

		onload: function (listview) {
			// Native/prior onload runs first (chained by the helper), then this inner button.
			listview.page.add_inner_button(__("AP Board"), function () {
				frappe.set_route("query-report", "FClist Supplier Balance");
			});
		},
	});
})();
