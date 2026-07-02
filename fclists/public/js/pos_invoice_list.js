// FClist — POS Invoice dense list.
// Chain an "is_return" indicator onto the native POS Invoice list and add a jump to the FClist POS Invoice
// board (tender-split Script Report). EXTEND, never replace: we call fclists.extend_listview() (defined in
// fclists_lib.js) so ERPNext's own list config for POS Invoice is preserved and merely augmented. A bare
// `frappe.listview_settings["POS Invoice"] = {...}` would clobber it (Frappe concatenates every app's
// list-js). Finding A.
(function () {
	"use strict";

	fclists.extend_listview("POS Invoice", {
		add_fields: ["is_return", "status", "docstatus"],

		get_indicator: function (doc) {
			// Return receipt gets its own colour. Runs FIRST; returning undefined falls through to the
			// native/prior get_indicator (chained by the helper).
			if (cint(doc.is_return)) {
				return [__("Return"), "red", "is_return,=,1"];
			}
			// else: fall through to native (Paid / Consolidated / Draft …).
		},

		onload: function (listview) {
			// Native/prior onload runs first (chained by the helper), then this inner button.
			listview.page.add_inner_button(__("POS Board"), function () {
				frappe.set_route("query-report", "FClist POS Invoice");
			});
		},
	});
})();
