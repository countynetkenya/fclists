// FClist Item Stock — filters. QBO-POS density parity: on-hand + cost-plus + velocity.
frappe.query_reports["FClist Item Stock"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "price_list",
			label: __("Selling Price List"),
			fieldtype: "Link",
			options: "Price List",
			get_query: function () {
				return { filters: { selling: 1 } };
			},
		},
		{
			fieldname: "window_days",
			label: __("Velocity Window (days)"),
			fieldtype: "Int",
			default: 30,
		},
	],
};
