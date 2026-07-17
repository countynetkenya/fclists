// FClist Item Stock — filters. QBO-POS density parity: on-hand + cost-plus + velocity.
// Companies (2026-07-17): tree-checkbox MultiSelectList yokoten — see fclist_gl.js's header comment for
// the full pattern-source note. No Cost Centre filter this wave — see fclist_item_stock.py's docstring.
frappe.query_reports["FClist Item Stock"] = {
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
