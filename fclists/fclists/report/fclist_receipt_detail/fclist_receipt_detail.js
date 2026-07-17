// FClist Receipt Detail — expandable per-receipt register. QB-POS "Sales Receipt Detail" parity.
// Native query-report tree: receipt rows expand to their item lines (collapsed by default, like QB-POS).
// Companies / Cost Centre (2026-07-17): tree-checkbox MultiSelectList yokoten — see fclist_gl.js's header
// comment for the full pattern-source note; same fclists.nav_options provider, same legacy-fallback shape.
frappe.query_reports["FClist Receipt Detail"] = {
	tree: true,
	name_field: "label",
	parent_field: "parent_label",
	initial_depth: 0,
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
		fclists.periods.filter_def(),
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "owner",
			label: __("Cashier"),
			fieldtype: "Link",
			options: "User",
		},
		{
			fieldname: "only_pos",
			label: __("POS only"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "show_items",
			label: __("Show Line Items"),
			fieldtype: "Check",
			default: 1,
		},
	],
};
