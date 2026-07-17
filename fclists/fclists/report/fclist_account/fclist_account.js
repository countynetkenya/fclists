// FClist Account — dense Chart-of-Accounts board filters. QBO COA density parity.
// Companies / Cost Centre (2026-07-17): tree-checkbox MultiSelectList yokoten — see fclist_gl.js's header
// comment for the full pattern-source note; same fclists.nav_options provider, same legacy-fallback shape.
// `reqd` dropped from the legacy Company Link (matching the other 9 upgraded reports' idiom) — the
// `companies` MultiSelectList is the preferred filter now, and forcing the legacy field would block a
// companies-only selection.
frappe.query_reports["FClist Account"] = {
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
			label: __("Cost Centre (scopes the live BALANCE only, not which accounts are listed)"),
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
