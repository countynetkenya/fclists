from frappe import _


def get_data():
	return [
		{
			"module_name": "FCLists",
			"category": "Modules",
			"label": _("FCLists"),
			"color": "green",
			"icon": "octicon octicon-list-unordered",
			"type": "module",
			"description": "Dense computed lists + QuickBooks-POS-style transaction histories.",
		}
	]
