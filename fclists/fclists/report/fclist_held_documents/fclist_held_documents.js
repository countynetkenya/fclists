// FClist Held Documents — parked NATIVE drafts board filters. QB-POS "Held" parity.
// Companies (2026-07-17): tree-checkbox MultiSelectList yokoten — see fclist_gl.js's header comment for
// the full pattern-source note. No Cost Centre filter this wave — see fclist_held_documents.py's docstring.
// FIRST .js FILE for this report (wave-1 shipped it with a `.py` that read filters.get(...) but no filter
// UI at all); this file closes that gap while wiring the new companies filter, exposing every filter the
// controller already reads (owner / limit).
frappe.query_reports["FClist Held Documents"] = {
	filters: [
		{
			fieldname: "companies",
			label: __("Companies (tree — a group selects its subtree)"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe
					.call({ method: "fclists.nav_options.company_tree_options", args: { txt: txt } })
					.then((r) => r.message);
			},
		},
		{
			fieldname: "company",
			label: __("Company (legacy — used only when Companies above is empty)"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "owner",
			label: __("Owner"),
			fieldtype: "Link",
			options: "User",
		},
		{
			fieldname: "limit",
			label: __("Limit (per doctype)"),
			fieldtype: "Int",
			default: 200,
		},
	],
};
