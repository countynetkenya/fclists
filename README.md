# FCLists

**Dense computed lists + QuickBooks-POS-style transaction histories for ERPNext.**

FCLists is a small, community, MIT-licensed ERPNext app. It adds the two things a plain Frappe List
View cannot give you out of the box:

1. **Dense computed lists (Script Reports).** On-hand quantity, valuation, reorder gaps, batch expiry,
   stock movement — numbers that are *computed* from `Bin` / `Stock Ledger Entry` / `Batch` and therefore
   cannot appear as columns on a normal list. FCLists ships these as role-gated Script Reports over the
   **native ERPNext doctypes** (Item, Bin, Stock Ledger Entry, Batch), so they respect your permissions
   and User Permissions automatically.

2. **QuickBooks-POS-style transaction histories.** Sales, POS, returns and payments presented the way a
   shopkeeper expects to read them — a running register of what was sold, returned and collected — built
   as Script Reports over `Sales Invoice`, `POS Invoice`, `Payment Entry`, `GL Entry`.

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
adds to the matching desk List View. Each is a native Script Report — computed live from your own tables,
filtered by your own permissions.

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
