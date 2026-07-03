// FClist Receipt Detail — expandable per-receipt register. QB-POS "Sales Receipt Detail" parity.
// Native query-report tree: receipt rows expand to their item lines (collapsed by default, like QB-POS).
frappe.query_reports["FClist Receipt Detail"] = {
	tree: true,
	name_field: "label",
	parent_field: "parent_label",
	initial_depth: 0,
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
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
