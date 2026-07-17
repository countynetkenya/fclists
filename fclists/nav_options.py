"""fclists.nav_options — the tree-checkbox (MultiSelectList) filter providers for FClist dense-list
reports: `company_tree_options` (Companies) and `cost_centre_tree_options` (Cost Centre), plus the two
server-side RESOLVERS (`resolve_companies_filter` / `resolve_cost_centre_filter`) every upgraded report's
`_data(filters)` calls to turn a tree selection into a plain `company/cost_center IN (...)` list.

PATTERN SOURCE (cited per the clean-room law): this is fclists' OWN thin copy of the tree-checkbox idiom
`fcbi/fcbi/consolidate.py` shipped 2026-07-16 (`company_tree_options` / `cost_centre_tree_options` /
`resolve_companies`) — permission-engine `frappe.get_list`, lft (NestedSet pre-order) ordering, breadcrumb
descriptions, `_Test` fixture filtering, is_group subtree expansion. **fclists imports NOTHING from fcbi**
(D-048/D-049 clean-room law: `required_apps == ["erpnext"]` exactly) — every app carries its own copy of
this pattern, the same way `fclists/periods.py` already duplicates `fcreports/periods.py`'s fiscal-anchor
idiom rather than importing it (see that module's own docstring).

THE DIFFERENCE FROM fcbi's VERSION: fcbi's `consolidate.py` composes a strict "Group Company" gate
(`group_entities`) alongside the lenient tree resolver, because its Consolidated PnL report needs BOTH a
legacy is_group-only path and the new free-mixing path. FClist reports never had a group-only mode — every
one of them already took a single leaf-or-group `company` Link filter — so `resolve_companies_filter` here
is the ONLY resolver, and it folds the "legacy single Link still works" contract in directly: an empty/absent
`companies` selection falls back to `[company]` (or `[]` — "no restriction" — when neither is set), so a
caller never needs an if/else at the report call site.

SECURITY BOUNDARY STAYS WHERE IT ALREADY WAS: every FClist report's row query runs through
`frappe.get_list` against GL Entry / Sales Invoice / Purchase Invoice / POS Invoice — permission-checked,
User-Permission-scoped, exactly as each report's own docstring already documents. Passing a foreign
company/cost-centre name in the `IN (...)` list changes nothing about that boundary (frappe.get_list still
refuses/omits rows the viewer cannot read) — these resolvers are lenient UX conveniences (unknown/foreign
names are silently dropped, never a throw), not a second security gate. `company_tree_options` additionally
only OFFERS permitted companies (see its docstring) so a scoped viewer's tree never surfaces a foreign name
to pick in the first place.

v16-safe: no frappe.db.commit; no raw SQL (frappe.get_list/get_all only). Sector-neutral, no client literal.
"""

import frappe
from frappe import _


# ---------------------------------------------------------------------------
# Company tree
# ---------------------------------------------------------------------------


def _permitted_companies():
    """The session user's companies via the PERMISSION ENGINE (role perms + Company User Permissions).
    frappe.get_list, never get_all — same one-line idiom as fcbi.compare.permitted_companies()."""
    return [c.name for c in frappe.get_list("Company", fields=["name"], limit_page_length=0)]


def _ancestor_chain(name, by_name, max_depth=50):
    """Ancestor names from `name`'s immediate parent up to the root (order as walked; caller reverses
    for a root-first breadcrumb). Cycle-guarded exactly like fcbi.consolidate._ancestor_chain — a repeat
    or a chain past `max_depth` simply stops instead of hanging on bad parent_company data."""
    chain, seen = [], set()
    node = by_name.get(name)
    parent = node.get("parent_company") if node else None
    while parent and parent in by_name and parent not in seen and len(chain) < max_depth:
        seen.add(parent)
        chain.append(parent)
        parent = by_name[parent].get("parent_company")
    return chain


@frappe.whitelist()
def company_tree_options(txt=None):
    """MultiSelectList `get_data` for the "Companies" filter on every upgraded FClist report: the
    viewer's PERMITTED companies (`_permitted_companies()`) PLUS any is_group=1 ANCESTORS needed for tree
    context (so a scoped viewer still sees "Emerald Ridge Group ▸" above their own entity, even though
    they cannot select a foreign sibling under it). Ordered by lft (native NestedSet pre-order).

    Each option is {"value": name, "description": tree_path}: a GROUP company gets the fixed description
    "(group — selects all descendants)"; a LEAF company gets its ancestor breadcrumb (e.g. "Emerald Ridge
    Group ▸") or "" when it has no group parent. `txt` filters case-insensitively on a substring of `name`,
    applied AFTER the permitted+ancestor set is built (a search never leaks a foreign name into view).

    Read-only; never the actual security boundary — see this module's docstring."""
    permitted = set(_permitted_companies())
    if not permitted:
        return []

    rows = frappe.get_all(
        "Company",
        fields=["name", "is_group", "lft", "rgt", "parent_company"],
        order_by="lft asc",
        limit_page_length=0,
    )
    by_name = {r.name: r for r in rows}

    wanted = set()
    for row in rows:
        if row.name in permitted:
            wanted.add(row.name)
            for ancestor in _ancestor_chain(row.name, by_name):
                wanted.add(ancestor)

    needle = (txt or "").lower()
    options = []
    for row in rows:  # already lft-ordered
        if row.name not in wanted:
            continue
        if row.name.startswith("_Test"):
            continue  # frappe test fixtures (allow_tests benches) — never a director-dropdown row
        if needle and needle not in row.name.lower():
            continue
        if row.is_group:
            description = _("(group — selects all descendants)")
        else:
            chain = list(reversed(_ancestor_chain(row.name, by_name)))
            description = " ▸ ".join(chain) + " ▸" if chain else ""
        options.append({"value": row.name, "description": description})
    return options


def resolve_companies_filter(companies=None, company=None):
    """Merge the new MultiSelectList `companies` filter with the legacy single `company` Link filter for
    a report's `_data(filters)`. `companies` (a list, or the MultiSelectList JSON string frappe sends)
    WINS when non-empty: each item is expanded — an is_group=1 Company to its is_group=0 lft/rgt
    descendants, a leaf kept as itself — same expansion idiom as fcbi.consolidate.resolve_companies().
    Unknown/foreign names are silently dropped (lenient UX, not a security gate — see module docstring).

    Falls back to `[company]` when `companies` is empty/absent and `company` is set — the ORIGINAL
    single-Link filter every FClist report shipped with keeps working untouched.

    Returns a de-duplicated list of Company names in lft (tree) order, or `[]` when NEITHER filter is
    set. Callers must treat `[]` as "no restriction" and omit the `company` key entirely — passing an
    empty `in` list to frappe.get_list would wrongly return zero rows instead of every permitted row."""
    if isinstance(companies, str):
        companies = frappe.parse_json(companies)
    companies = list(companies or [])
    if not companies:
        return [company] if company else []

    rows = frappe.get_all(
        "Company", fields=["name", "is_group", "lft", "rgt"], order_by="lft asc", limit_page_length=0,
    )
    by_name = {r.name: r for r in rows}

    resolved = {}  # name -> lft (dedupe + carries tree order for the final sort)
    for name in companies:
        row = by_name.get(name)
        if not row:
            continue  # unknown/foreign name — dropped, never a throw (dense-list filter, not a gate)
        if row.is_group:
            for d in rows:
                if d.lft > row.lft and d.rgt < row.rgt and not d.is_group:
                    resolved[d.name] = d.lft
        else:
            resolved[name] = row.lft
    return [name for name, _lft in sorted(resolved.items(), key=lambda kv: kv[1])]


# ---------------------------------------------------------------------------
# Cost Centre tree
# ---------------------------------------------------------------------------


@frappe.whitelist()
def cost_centre_tree_options(txt=None, companies=None):
    """MultiSelectList `get_data` for the "Cost Centre" filter — via `frappe.get_list` (the permission
    engine; a scoped viewer never sees a foreign company's cost centres), optionally restricted to
    `companies` (a MultiSelectList JSON string OR a plain list — parsed defensively, same contract
    `resolve_companies_filter` uses). Ordered company-then-lft (a valid PER-COMPANY tree pre-order —
    companies are never interleaved).

    Each option is {"value": name, "description": "<company abbr> · <parent chain>"} — group Cost
    Centres ARE included (a group value is a coarser, still-valid pick; see resolve_cost_centre_filter,
    which expands it server-side exactly like a group Company)."""
    if isinstance(companies, str):
        companies = frappe.parse_json(companies)
    filters = {}
    if companies:
        filters["company"] = ["in", list(companies)]

    rows = frappe.get_list(
        "Cost Center",
        filters=filters,
        fields=["name", "company", "parent_cost_center", "is_group", "lft"],
        order_by="company asc, lft asc",
        limit_page_length=0,
    )
    by_name = {r.name: r for r in rows}
    abbr_by_company = {}

    needle = (txt or "").lower()
    options = []
    for row in rows:
        if needle and needle not in row.name.lower():
            continue
        company = row.company
        if company not in abbr_by_company:
            abbr_by_company[company] = frappe.db.get_value("Company", company, "abbr") or company
        chain = []
        seen, parent = set(), row.parent_cost_center
        while parent and parent in by_name and parent not in seen:
            seen.add(parent)
            chain.append(by_name[parent].name)
            parent = by_name[parent].parent_cost_center
        chain.reverse()
        parent_chain = " ▸ ".join(chain)
        description = (
            f"{abbr_by_company[company]} · {parent_chain}" if parent_chain else abbr_by_company[company]
        )
        options.append({"value": row.name, "description": description})
    return options


def resolve_cost_centre_filter(cost_centers=None):
    """The Cost Centre analogue of `resolve_companies_filter`: expand any is_group=1 Cost Centre
    selection to its is_group=0 lft/rgt descendants (a group value is a coarser, still-valid pick — see
    cost_centre_tree_options), keep a leaf as itself, drop unknown names silently. `cost_centers` is a
    list, or the MultiSelectList JSON string frappe sends.

    Returns a de-duplicated list of Cost Center names in lft (tree) order, or `[]` when unset — callers
    must treat `[]` as "no restriction" (never pass an empty `in` list to frappe.get_list)."""
    if isinstance(cost_centers, str):
        cost_centers = frappe.parse_json(cost_centers)
    cost_centers = list(cost_centers or [])
    if not cost_centers:
        return []

    rows = frappe.get_all(
        "Cost Center",
        fields=["name", "is_group", "lft", "rgt"],
        order_by="lft asc",
        limit_page_length=0,
    )
    by_name = {r.name: r for r in rows}

    resolved = {}
    for name in cost_centers:
        row = by_name.get(name)
        if not row:
            continue
        if row.is_group:
            for d in rows:
                if d.lft > row.lft and d.rgt < row.rgt and not d.is_group:
                    resolved[d.name] = d.lft
        else:
            resolved[name] = row.lft
    return [name for name, _lft in sorted(resolved.items(), key=lambda kv: kv[1])]
