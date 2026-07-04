# FCLists

**Dense computed lists + QuickBooks-POS-style transaction histories for ERPNext.**

FCLists is a small, community, MIT-licensed ERPNext app. It adds the three things a plain Frappe List
View cannot give you out of the box:

1. **Dense computed lists (Script Reports).** On-hand quantity, valuation, reorder gaps, batch expiry,
   stock movement, AR/AP balances, aging buckets, live account balances, best-sellers by velocity — numbers
   that are *computed* from `Bin` / `Stock Ledger Entry` / `Batch` / `Sales Invoice` / `GL Entry` and therefore
   cannot appear as columns on a normal list. FCLists ships these as role-gated Script Reports over the
   **native ERPNext doctypes** (Item, Bin, Stock Ledger Entry, Batch, Customer, Supplier, Account, GL Entry).
   **What is enforced:** your native **roles gate each report** (you must hold one of its roles to open it),
   and every row-producing query runs permission-checked (`frappe.get_list`). **User Permissions scope the
   rows for doctypes that carry the restricted link field** — a user restricted to Company A never sees
   Company B's ledger, AR or sales rows (Sales/Purchase Invoice, Payment Entry, GL Entry, Account and Stock
   Ledger Entry all carry `company`). Item- and Batch-driven boards have no company field, so they are
   role-gated and read-checked but **not company-partitioned**. Column enrichments (prices, credit limits,
   tender labels) describe rows you are already permitted to see.

2. **QuickBooks-POS-style transaction histories.** Sales, POS, returns and payments presented the way a
   shopkeeper expects to read them — a running register of what was sold, returned and collected — built
   as Script Reports over `Sales Invoice`, `POS Invoice`, `Purchase Invoice`, `Payment Entry`, `GL Entry`.

3. **Native Business Intelligence — dashboards, charts and KPI cards (no Insights required).** A ready-made
   dashboard, trend/rank charts and at-a-glance number cards built entirely on **frappe core** doctypes
   (Dashboard / Dashboard Chart / Number Card). See [Business Intelligence](#business-intelligence) below.

FCLists also enriches the built-in List Views (Item, Batch, Sales Invoice, POS Invoice) with helpful
indicators and a jump-to-report button. It does this the **safe** way — it *extends* the native list
settings rather than replacing them, using the reusable `fclists.extend_listview()` helper (documented
[below](#reusable-fclistsextend_listview)) — so nothing ERPNext already put on those lists is lost.

## What FCLists is not

- It is **not** a fork of ERPNext. It adds no business logic to your ledger and overrides no core class.
- It has **no client-specific behaviour**. Everything is sector-neutral and config-driven
  (a site can turn the whole app off with `fclists_enabled: false` in `site_config.json`).
- It depends on **ERPNext only**. It does not require or import any other app.

## Requirements

- Frappe / ERPNext **v16**
- Python 3.14+, Node 24+

## Installation

Install with the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/countynetkenya/fclists --branch main
bench --site your.site install-app fclists
```

That's it — no fixtures to import, no roles to create. The reports **reuse your existing ERPNext Stock
and Accounts roles**, so a user sees a report only if they already hold one of its native roles. Nothing
is world-readable.

To upgrade later, `bench get-app` again (or `git pull` in `apps/fclists`) and run
`bench --site your.site migrate`.

## What each list gives you

Reach any report from **Reports** (search its name in the awesomebar) or from the jump button FCLists
adds to the matching desk List View. Each is a native Script Report — computed live from your own tables.
Your roles gate whether a report opens at all; your User Permissions (e.g. a Company restriction) scope
which rows it shows you *on doctypes that carry that link field* (invoices, payments, GL, accounts — the
Item/Batch boards have no company field and are role-gated only).

#### Wave-1 — stock boards & POS/sales histories

| Report (open by this name) | Over | Roles that can read it | What it gives you |
|---|---|---|---|
| **FClist Item Stock** | Item / Bin | Stock User, Stock Manager, Accounts Manager, System Manager | Per item: on-hand qty (summed across warehouses), valuation, selling price, margin & margin%, reorder level, units sold in the last N days (velocity). |
| **FClist Reorder** | Item | Stock User, Stock Manager, System Manager | Only items at or below their reorder level, with the shortfall and default supplier. |
| **FClist Batch Expiry** | Batch | Stock User, Stock Manager, System Manager | Every batch with an expiry date, earliest-first (FEFO): days-to-expiry, qty remaining, Expired/Expiring/OK status. |
| **FClist Stock Movement** | Stock Ledger Entry | Stock User, Stock Manager, System Manager | Recent stock moves with the signed qty split into clear *in* / *out* columns, plus the causing voucher. |
| **FClist Sales History** | Sales Invoice | Accounts User, Accounts Manager, System Manager | A chronological register of every sales receipt with a link to open/print it; filter by date, customer, cashier. |
| **FClist Sales Invoice** | Sales Invoice | Accounts User, Accounts Manager, System Manager | Every sales invoice with total, outstanding, status and a computed *Overdue* flag. |
| **FClist POS Invoice** | POS Invoice | Accounts User, Accounts Manager, System Manager | Every POS receipt with its tender split (e.g. Cash: 500, M-Pesa: 1200) and a return flag. |
| **FClist Returns** | Sales Invoice | Accounts User, Accounts Manager, System Manager | Every return (credit note): date, customer, the invoice returned against, amount. |
| **FClist Payments** | Payment Entry | Accounts User, Accounts Manager, System Manager | Every incoming payment: party, amount, mode of payment, bank / M-Pesa reference. |

#### Wave-2 — AR / AP density (who owes what, and how overdue)

| Report (open by this name) | Over | Roles that can read it | What it gives you |
|---|---|---|---|
| **FClist Customer Balance** | Customer | Accounts User, Accounts Manager, System Manager | The QuickBooks 3-field AR glance per customer: outstanding, credit limit, available credit and the past-due portion — all aggregated live from submitted Sales Invoices against today. |
| **FClist Supplier Balance** | Supplier | Accounts User, Accounts Manager, System Manager | The AP mirror: per supplier we owe, total outstanding and the past-due portion, aggregated live from submitted Purchase Invoices. |
| **FClist Open Invoices** | Sales Invoice | Accounts User, Accounts Manager, System Manager | The A/R aging worklist — one row per unpaid invoice, tagged with its aging bucket (Current, 1-30, 31-60, 61-90, 90+) and days-past-due. |
| **FClist Purchase Invoice** | Purchase Invoice | Accounts User, Accounts Manager, System Manager | The AP mirror of FClist Sales Invoice: every purchase invoice with total, outstanding, status and a computed *Overdue* flag. |

#### Wave-2 — Finance (ledger, chart of accounts, reconciliation)

| Report (open by this name) | Over | Roles that can read it | What it gives you |
|---|---|---|---|
| **FClist Account** | Account | Accounts User, Accounts Manager, System Manager | The whole chart of accounts in one dense board with a *live balance* per account (summed from GL Entry as of a date), plus type, root type and group flag. |
| **FClist GL** | GL Entry | Accounts User, Accounts Manager, System Manager | The QuickBooks-style ledger scroll — newest-first GL entries with debit/credit, voucher, party and remarks, filterable by account, party and date. |
| **FClist Bank Reconciliation Queue** | Payment Entry | Accounts User, Accounts Manager, System Manager | Every submitted Payment Entry not yet cleared (the "For Review" queue) — works for bank *and* mobile-money, reading only native Payment Entry fields. |

#### Wave-2 — BI-flavoured Script Reports (best-sellers, velocity, breakdowns)

| Report (open by this name) | Over | Roles that can read it | What it gives you |
|---|---|---|---|
| **FClist Best Sellers** | Sales Invoice Item | Stock User, Stock Manager, Accounts User, Accounts Manager, System Manager | Top items by units sold over a window (velocity = sales-rank): rank, qty sold, revenue and margin per item. |
| **FClist Sales by Cashier** | Sales Invoice | Accounts User, Accounts Manager, System Manager | Sales grouped by the invoice owner (the cashier at the counter): invoice count, total and average sale. |
| **FClist Sales by Department** | Sales Invoice Item | Accounts User, Accounts Manager, System Manager | Sales grouped by item group ("department"): qty, revenue and share-% of total revenue. |
| **FClist Sales YoY** | Sales Invoice | Accounts User, Accounts Manager, System Manager | The QuickBooks dashboard glance: Today / WTD / MTD / YTD this year vs the same period last year, with the % change. |

#### Wave-3 — QB-POS parity borrows (the reconciliation matrix & the receipt drill-down)

| Report (open by this name) | Over | Roles that can read it | What it gives you |
|---|---|---|---|
| **FClist Payment Summary** | Sales Invoice | Accounts User, Accounts Manager, System Manager | The QuickBooks-POS day × tender reconciliation matrix: one row per day, one Currency column per mode of payment actually used (net of change given), an *On Account* column for credit sales, and a daily total. |
| **FClist Receipt Detail** | Sales Invoice | Accounts User, Accounts Manager, System Manager | The QuickBooks-POS expandable receipt register: per receipt — date, time, Sales/Return, customer, qty, total, tender, cashier, line count — expanding (tree) to its item lines with qty, rate and amount. |

A **login-gated user guide** ships with the app at `/fclists-guide` (gated to those same Stock and
Accounts roles) — a task-shaped walkthrough for end users.

### List View additions

Open any of these desk List Views and FCLists adds an indicator plus a one-click jump to the matching
board — layered *on top of* ERPNext's own list config, never replacing it:

| List View | Indicator added | Jump button |
|---|---|---|
| Item | *Disabled* | **Stock Board** → FClist Item Stock |
| Batch | *Expired* / *Expiring* | **Expiry Board** → FClist Batch Expiry |
| Sales Invoice | *Overdue* / *Unpaid* | **Sales History** → FClist Sales History |
| POS Invoice | *Return* | **POS Board** → FClist POS Invoice |
| Customer | *Disabled* | **AR Board** → FClist Customer Balance |
| Supplier | *On Hold* / *Disabled* | **AP Board** → FClist Supplier Balance |
| Purchase Invoice | *Overdue* / *Unpaid* | **Purchase Board** → FClist Purchase Invoice |
| Account | *Group* / root-type | **Balances** → FClist Account |

## Business Intelligence

FCLists ships a small **native BI layer** so you get dashboards and KPI glances the moment the app is
installed — **no Frappe Insights, no external BI tool, and no extra dependency required.** Everything is
built on **frappe core** doctypes that every ERPNext site already has:

- **Dashboard — `FCLists BI`.** A ready-made dashboard you can open from *Dashboard* in the desk. It lays
  out the charts and cards below in one place; pin it or set it as your home dashboard.
- **Dashboard Charts.** *FClist Sales Trend* (a monthly sales line over the last year) and *FClist Top
  Customers* (a bar chart of the ten highest-billed customers) — both grouped/summed by frappe over native
  `Sales Invoice`, filtered to submitted docs only.
- **Number Cards (KPI glances).** Five at-a-glance counters, each role-gated on its own `roles` table:
  *FClist Items Below Reorder* and *FClist Batches Expiring ≤30d* (Stock roles), and *FClist Overdue
  Invoices*, *FClist Total Sales MTD* and *FClist Overdue AR* (Accounts roles). Drop any of them onto your
  own workspace or dashboard.

These are shipped as **fixtures** (`Dashboard`, `Dashboard Chart`, `Number Card`), so `bench install-app` /
`bench migrate` seeds them automatically. They are additive and upgrade-safe, and every fixture name is
prefixed `FCLists`/`FClist` so it never collides with — or overwrites — another app's cards or charts.

A few properties worth knowing:

- **Native, not a fork.** The BI layer adds no new BI engine. It composes the same `Dashboard` /
  `Dashboard Chart` / `Number Card` doctypes you'd build by hand — FCLists just ships them pre-wired.
- **Role-safe by construction.** Number Cards count/sum over native doctypes with **no client-specific
  filters** and are role-gated, so a card never surfaces a figure to someone who couldn't already see it.
  The best-sellers / velocity / breakdown *reports* (see the tables above) give you the deeper drill-downs.
- **Insights-friendly, Insights-optional.** If you *do* run Frappe Insights, these lists and reports are a
  natural data source to point it at — but FCLists never requires it, and works fully without it.

## Reusable: `fclists.extend_listview()`

**The safe primitive for adding to a List View from your own app.** Frappe concatenates the list-view
JavaScript of *every* installed app into one bundle, and they all mutate the same global —
`frappe.listview_settings`. So the common shortcut

```js
// ❌ DON'T — a bare reassignment silently clobbers ERPNext's (and every other app's) config
frappe.listview_settings["Item"] = { onload() { /* ... */ } };
```

means the **last file to load wins** and throws away everything the earlier ones put there — including
ERPNext's own native list configuration for that doctype (its indicators, buttons, `add_fields`, …). The
list looks subtly broken and nobody knows why.

FCLists ships `fclists.extend_listview(doctype, extension)` (loaded on every desk page via `app_include_js`)
to do the merge safely. It:

- **concatenates** `add_fields` (so no contributor's columns get dropped),
- **chains** `onload` — the previously-registered handler runs first, then yours,
- **chains** `get_indicator` — yours runs first; return nothing to fall through to the previous handler,
- **shallow-merges** every other key via `Object.assign`.

**Copy-paste example** (this is exactly how FCLists' own `item_list.js` is written — reuse the pattern in
your app):

```js
// your_app/public/js/item_list.js — declared in hooks.py:
//   doctype_list_js = {"Item": "public/js/item_list.js"}
// (fclists must be installed so fclists.extend_listview is loaded before this runs)
fclists.extend_listview("Item", {
    // Concatenated onto native + any other app's add_fields — never replaces them.
    add_fields: ["disabled", "item_group"],

    // Runs FIRST; return undefined to fall through to the previously-registered indicator (chained).
    get_indicator: function (doc) {
        if (cint(doc.disabled)) {
            return [__("Disabled"), "gray", "disabled,=,1"];
        }
        // return nothing => native / prior indicator decides the other states
    },

    // Native/prior onload runs first, THEN this — your button is added on top, nothing is lost.
    onload: function (listview) {
        listview.page.add_inner_button(__("Stock Board"), function () {
            frappe.set_route("query-report", "FClist Item Stock");
        });
    },
});
```

The helper returns the merged settings object (also stored back on `frappe.listview_settings[doctype]`).
Call it once per doctype per file. See `fclists/public/js/fclists_lib.js` for the fully-commented source.

## License

MIT
