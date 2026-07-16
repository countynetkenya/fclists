# fclists — Claude Code Context

**Boot:** `../CLAUDE.md` (lean) → `../STATE.md`. Load `../sw/*` per task — **always `../sw/anti-reinvention.md` before building.**
**Skills:** `/frappe-dev` (how-to-implement); `/frappe-data-access` (querying). On conflict, `../sw/` wins.

---

## App Identity

| Key | Value |
|---|---|
| Name (package) | `fclists` |
| Title | FCLists |
| Publisher | Flowcore · License **MIT** |
| Purpose | **Standalone COMMUNITY app (REGISTRY D-048):** QuickBooks-POS transaction histories + dense computed lists over native ERPNext data. The single **LISTS provider** for the constellation. |
| `required_apps` | **`["erpnext"]` ONLY** (clean-room law — see below) |
| Server path | symlink `~/bench-dev/apps/fclists` → this repo (NEVER `rm` the bench path) |
| Module | `FCLists` (package `fclists`, module dir `fclists/fclists/fclists/`) |
| Product framing | FCDesk-**Books** is the bookkeeper product name (D-040); `fclists` is the developer-facing LISTS infra it composes. |

## The clean-room law (D-048/D-049 — non-negotiable)

`fclists` is installable by the **whole Frappe community**, so it stays a clean-room app:
- **`required_apps` = exactly `["erpnext"]`.** NEVER add a Flowcore-family app (`flowcore`, `fcmuster`, `settle`, `fcbi`, …) — not as a dep, not as an import. Keep the hooks list at `["erpnext"]`.
- Composes **NATIVE ERPNext doctypes only** (Item, Bin, Stock Ledger Entry, Batch, Sales/POS/Purchase Invoice, Payment Entry, GL Entry, Account, Customer, Supplier). Reuses **native roles** — no seeded roles.
- **No client literals (D-002):** no company/branch/school names, no `custom_*` client fields in logic. Every report/card is role-safe for any tenant.
- **MIT, clean-room reconstruction only** — never lift AGPL/GPL app source.

## What fclists owns vs reuses (anti-reinvention)

| Reuse / compose (never rebuild) | Build (net-new) |
|---|---|
| Native list view, Query Report engine, GL/stock ledgers = source of truth | **~26 Script Reports** (`report/fclist_*`) — QBPOS transaction histories + dense computed lists |
| Native Dashboard / Dashboard Chart / **Number Card** (core, NO hard dep on Insights or any BI app) | **`extend_listview()` loader primitive** — dense inline columns/badges on native list views |
| v16 desk shell + Workspace Sidebar nav (D-073) | period-preset filter (`fclists.periods.*`) — QBO-style "Report period" splice |

## Loader primitives (hooks.py)

- **`app_include_js`** loads on every desk page: `fclists_lib.js` (defines `fclists.extend_listview(...)`) + `fclists_periods.js` (`fclists.periods.*` date presets).
- **`doctype_list_js`** — Wave-1 (Item / Batch / Sales Invoice / POS Invoice) + Wave-2 (Customer / Supplier / Purchase Invoice / Account). Each file **EXTENDS** via `fclists.extend_listview()` — **never** a bare `frappe.listview_settings["X"] = {...}` reassignment (Frappe concatenates every app's list-js; a bare assign clobbers ERPNext's own config — Finding A).

## Reports at a glance (`fclists/fclists/report/fclist_*`)

Sales: `sales_history` · `sales_invoice` · `pos_invoice` · `receipt_detail` · `sales_by_cashier` · `sales_by_department` · `best_sellers` · `sales_yoy` · `returns` · `payment_summary` · `payments`.
Purchasing/AP-AR: `purchase_invoice` · `receiving` · `open_invoices` · `customer_balance` · `supplier_balance` · `held_documents`.
Stock: `item_stock` · `stock_movement` · `reorder` · `batch_expiry` · `cost_adjustment` · `duplicate_items`.
Finance: `gl` · `account` · `bank_reconciliation_queue`.

## Desk surface + fixtures (D-073 nav standard)

- **Workspace `FCLists`** (`fclists/fclists/workspace/fclists/`) — surface class **`app-domain`** (Records · Reports · Lists · Guide); single-source icon; **`Workspace Sidebar` shipped as a fixture** (else desk auto-snapshots + freezes a stale sidebar on first visit — S033 bug).
- **Desktop Icon** `fclists/desktop_icon/fclists.json`; `add_to_apps_screen` + route `/desk/fclists` (v16 base — never author `/app/` URLs).
- **Number Cards** (fixtures, name-prefixed `FClist %`, role-gated on their own `roles` table): Items-Below-Reorder · Batches-Expiring-30d · Overdue-Invoices · Total-Sales-MTD · Overdue-AR. Also `Dashboard Chart` / `Dashboard` fixtures (prefix `FCLists%`). **Prefix-scoped filters only** — Number Card/Dashboard are SHARED doctypes; a bare `{"dt": "Number Card"}` would export/overwrite other apps' cards.
- **KPI head** (D-073 §4A): the mandatory KPI slot is filled by **`fcbi.kpi.*` at render-time as a dotted STRING**, never an import — so composing fcbi does NOT make it a `required_app`. The clean-room law holds.

## Verify

- **`../scripts/verify.sh fclists`** — the live verifier `scripts/_verify_fclists.py` (in the default set). Bar: **156/156**, hermetic tests **65/65**. Published PUBLIC (D-048, 2026-07-03).
- Tests: `fclists/fclists/tests/`. See `../sw/testing.md` for the tested-done bar (live verifier w/ DENY + `all_ok` masking-proof + hermetic + Vitest; NO false-greens).
- User guide: `../fclists/fclists/www/fclists-guide` (D-017 gate).

## Notes / debt

- After hooks/JS changes: **restart the bench** (`../scripts/_restart_bench.sh`) + `bench build --app fclists` (workers + assets cache).
- Data-writing checks run on the **playground twins**, never real client companies (see MEMORY: test-on-playground-twins).
- Governance: commit + push to `countynetkenya/fclists` are AUTONOMOUS (jidoka-gated); staging/prod deploys stay GMD-gated.
