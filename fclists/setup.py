"""fclists setup hooks — idempotent, migrate-safe configuration.

Run from ``after_migrate`` (outside any doc lifecycle): must be idempotent and must NOT call
``frappe.db.commit()`` (the migrate harness commits). Wrapped so a failure logs and never breaks a
migrate.

**By design this is a documented no-op seam.** FCLists' Script Reports reuse the NATIVE ERPNext Stock
and Accounts roles (Stock User, Stock Manager, Accounts User, Accounts Manager, System Manager) — the
roles are populated on each Report doc's ``roles`` table, so a user sees a report only if they already
hold one of those native roles. FCLists therefore creates NO new role and needs NO seeding.

If a future wave ever needs to seed something (e.g. a capability flag row, a default filter preset),
add it inside ``ensure()`` below — keeping it idempotent (check-then-write) and commit-free.
"""

import frappe


def after_migrate():
	"""Entry point wired in hooks.py. Wrapped so a failure logs and never breaks a migrate."""
	try:
		ensure()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "fclists.setup.after_migrate")


def ensure():
	"""Idempotent, commit-free configuration seam.

	Intentionally empty today: FCLists reuses native roles and adds no seeded data. This function exists
	as the single, documented place for the next wave to add idempotent setup (never a client literal —
	drive any behaviour from ``site_config`` per Finding / naming law). Leave it callable and no-op-safe.
	"""
	return None
