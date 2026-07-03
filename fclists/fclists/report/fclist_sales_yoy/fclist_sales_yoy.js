// FClist Sales YoY — the QuickBooks dashboard. Company filter only; periods computed server-side.
frappe.query_reports["FClist Sales YoY"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
	],
};
