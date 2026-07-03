// FClist Open Invoices — A/R aging worklist filters (unpaid Sales Invoices, bucketed by days past due).
frappe.query_reports["FClist Open Invoices"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
	],
};
