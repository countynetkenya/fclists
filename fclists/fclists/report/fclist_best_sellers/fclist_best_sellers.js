// FClist Best Sellers — velocity / sales-rank filters (window = velocity window, top-N cutoff).
frappe.query_reports["FClist Best Sellers"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
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
