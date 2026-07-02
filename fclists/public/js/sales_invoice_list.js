// FClist — Sales Invoice dense list.
// Chain an overdue/unpaid indicator onto the native Sales Invoice list and add a jump to the QuickBooks-style
// "Sales History" Script Report. EXTEND, never replace: we call fclists.extend_listview() (defined in
// fclists_lib.js) so ERPNext's own list config for Sales Invoice — its indicators, buttons, add_fields — is
// preserved and merely augmented. A bare `frappe.listview_settings["Sales Invoice"] = {...}` would clobber it
// (Frappe concatenates every app's list-js). Finding A.
(function () {
	"use strict";

	fclists.extend_listview("Sales Invoice", {
		// Fetch what our indicator needs (concatenated onto native add_fields, never replacing them).
		add_fields: ["outstanding_amount", "due_date", "status", "docstatus"],

		get_indicator: function (doc) {
			// Overdue: submitted, money still owed, past due date. Runs FIRST; returning undefined
			// falls through to the native/prior get_indicator (chained by the helper).
			if (
				cint(doc.docstatus) === 1 &&
				flt(doc.outstanding_amount) > 0 &&
				doc.due_date &&
				frappe.datetime.get_diff(doc.due_date, frappe.datetime.get_today()) < 0
			) {
				return [__("Overdue"), "red", "outstanding_amount,>,0|due_date,<,Today"];
			}
			if (cint(doc.docstatus) === 1 && flt(doc.outstanding_amount) > 0) {
				return [__("Unpaid"), "orange", "outstanding_amount,>,0"];
			}
			// else: fall through to native (Paid / Return / Draft / Cancelled …).
		},

		onload: function (listview) {
			// Native/prior onload runs first (chained by the helper), then this inner button.
			listview.page.add_inner_button(__("Sales History"), function () {
				frappe.set_route("query-report", "FClist Sales History");
			});
		},
	});
})();
