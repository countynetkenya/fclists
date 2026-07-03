// FClist Account — dense Chart-of-Accounts board filters. QBO COA density parity.
frappe.query_reports["FClist Account"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "root_type",
			label: __("Root Type"),
			fieldtype: "Select",
			options: ["", "Asset", "Liability", "Equity", "Income", "Expense"].join("\n"),
		},
		{
			fieldname: "as_of_date",
			label: __("As of Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
	],
};
