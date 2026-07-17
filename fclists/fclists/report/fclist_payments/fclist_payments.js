// FClist Payments — payments RECEIVED board filters. QBO-POS "Received Payments" parity.
// Companies (2026-07-17): tree-checkbox MultiSelectList yokoten — see fclist_gl.js's header comment for
// the full pattern-source note. No Cost Centre filter here — Payment Entry carries no header cost_center
// field this wave (see fclist_payments.py's docstring).
frappe.query_reports["FClist Payments"] = {
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
			fieldname: "mode_of_payment",
			label: __("Mode of Payment"),
			fieldtype: "Link",
			options: "Mode of Payment",
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "Data",
		},
	],
};
