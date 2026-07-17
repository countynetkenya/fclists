// FClist GL — dense recent-ledger board filters. QBO General Ledger density parity.
// Companies / Cost Centre (2026-07-17): tree-checkbox MultiSelectList yokoten from
// fcbi_consolidated_pnl.js's pattern (fcbi/fcbi/consolidate.py provider) — fclists' OWN thin copy via
// fclists.nav_options.company_tree_options / cost_centre_tree_options (no cross-app import). The old
// single `company` Link stays as the visible legacy fallback (fclists.nav_options.resolve_companies_filter
// prefers `companies` when set).
frappe.query_reports["FClist GL"] = {
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
			fieldname: "account",
			label: __("Account"),
			fieldtype: "Link",
			options: "Account",
			get_query: function () {
				const company = frappe.query_report.get_filter_value("company");
				return { filters: company ? { company: company } : {} };
			},
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "Data",
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
	],
};
