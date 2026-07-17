// FClist Cost Adjustment — line-level stock REVALUATION register filters. QB-POS "Cost Adjustment" parity.
// Companies (2026-07-17): tree-checkbox MultiSelectList yokoten — see fclist_gl.js's header comment for
// the full pattern-source note. No Cost Centre filter this wave — see fclist_cost_adjustment.py's docstring.
// FIRST .js FILE for this report (wave-1 shipped it with a `.py` that read filters.get(...) but no filter
// UI at all); this file closes that gap while wiring the new companies filter, exposing every filter the
// controller already reads (item / window_days / from_date / to_date).
frappe.query_reports["FClist Cost Adjustment"] = {
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
			fieldname: "item",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		fclists.periods.filter_def(),
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "window_days",
			label: __("Window (days, used only when From/To Date are empty)"),
			fieldtype: "Int",
			default: 30,
		},
	],
};
