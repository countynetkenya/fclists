// FCLists — Item dense list (catalogue density parity).
// ----------------------------------------------------------------------------------------------------
// On-hand qty / margin / velocity are COMPUTED (Bin/SLE/Item Price joins) and belong in the
// "FClist Item Stock" Script Report — NOT on the Item table. So here we only enrich what already lives on
// the doctype (disabled/item_group/stock_uom) and offer a jump to the dense computed stock board.
//
// EXTEND, never replace: we go through fclists.extend_listview() (defined in fclists_lib.js), which
// merge-and-chains onto ERPNext's native Item listview config and any prior app's — a bare
// `frappe.listview_settings["Item"] = {...}` would clobber it (Finding A).
fclists.extend_listview("Item", {
	// Concatenated onto native + prior add_fields so our indicator has the data it needs.
	add_fields: ["disabled", "item_group", "stock_uom"],

	// Runs FIRST; returning nothing falls through to the previously-registered get_indicator (chained).
	get_indicator: function (doc) {
		if (cint(doc.disabled)) {
			return [__("Disabled"), "gray", "disabled,=,1"];
		}
		// return undefined => native / prior indicator decides the other states.
	},

	// Native/prior onload runs first, THEN this — inner button added on top.
	onload: function (listview) {
		listview.page.add_inner_button(__("Stock Board"), function () {
			frappe.set_route("query-report", "FClist Item Stock");
		});
	},
});
