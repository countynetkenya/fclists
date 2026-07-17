// FClist Best Sellers — velocity / sales-rank filters (window = velocity window, top-N cutoff).
// Companies / Cost Centre (2026-07-17): tree-checkbox MultiSelectList yokoten — see fclist_gl.js's header
// comment for the full pattern-source note; same fclists.nav_options provider, same legacy-fallback shape.
frappe.query_reports["FClist Best Sellers"] = {
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
			fieldname: "cost_center",
			label: __("Cost Centre"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe
					.call({
						method: "fclists.nav_options.cost_centre_tree_options",
						args: { txt: txt, companies: frappe.query_report.get_filter_value("companies") },
					})
					.then((r) => r.message);
			},
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "window_days",
			label: __("Window (days)"),
			fieldtype: "Int",
			default: 30,
		},
		{
			fieldname: "top_n",
			label: __("Top N"),
			fieldtype: "Int",
			default: 20,
		},
	],
};
