// FClist Batch Expiry — filters. FEFO board (generic; any perishable inventory).
frappe.query_reports["FClist Batch Expiry"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
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
			fieldname: "item",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Expired", "Expiring", "OK"].join("\n"),
		},
		{
			fieldname: "warn_days",
			label: __("Expiring Window (days)"),
			fieldtype: "Int",
			default: 30,
		},
		{
			fieldname: "show_depleted",
			label: __("Show Zero-Qty Batches"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
