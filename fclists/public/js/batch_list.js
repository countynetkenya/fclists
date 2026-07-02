// FCLists — Batch dense list (FEFO density parity).
// ----------------------------------------------------------------------------------------------------
// Qty-remaining per batch is COMPUTED (SLE sum) and belongs in the "FClist Batch Expiry" Script Report.
// Here we colour each batch by its native `expiry_date` (red = expired, orange = expiring soon) — both
// live on the Batch doctype — and offer a jump to the dense FEFO board.
//
// EXTEND, never replace: fclists.extend_listview() (fclists_lib.js) merge-and-chains onto ERPNext's
// native Batch listview config; a bare `frappe.listview_settings["Batch"] = {...}` would clobber it
// (Finding A). GENERIC — no sector literal (works for any perishable inventory).
fclists.extend_listview("Batch", {
	// expiry_date drives the indicator; item shown for context.
	add_fields: ["expiry_date", "item"],

	// Runs FIRST; returns nothing for batches without an expiry (or not expiring) so the previously-
	// registered get_indicator is chained.
	get_indicator: function (doc) {
		if (!doc.expiry_date) {
			return; // no expiry tracked → fall through to native / prior indicator
		}
		var today = frappe.datetime.get_today();
		var days = frappe.datetime.get_day_diff(doc.expiry_date, today);
		if (days < 0) {
			return [__("Expired"), "red", "expiry_date,<,Today"];
		}
		if (days <= 30) {
			return [__("Expiring"), "orange", "expiry_date,<=," + frappe.datetime.add_days(today, 30)];
		}
		// still fresh → let native / prior indicator decide.
	},

	// Native/prior onload runs first, THEN this — inner button added on top.
	onload: function (listview) {
		listview.page.add_inner_button(__("Expiry Board"), function () {
			frappe.set_route("query-report", "FClist Batch Expiry");
		});
	},
});
