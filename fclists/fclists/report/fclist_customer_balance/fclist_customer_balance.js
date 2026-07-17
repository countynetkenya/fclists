// FClist Customer Balance — QuickBooks AR board filters (per-customer outstanding / limit / past due).
// Companies (2026-07-17): tree-checkbox MultiSelectList yokoten — see fclist_gl.js's header comment for
// the full pattern-source note. No Cost Centre filter — Customer is a MASTER doctype with no cost_center
// column (see fclist_customer_balance.py's docstring).
frappe.query_reports["FClist Customer Balance"] = {
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
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
	],
};
