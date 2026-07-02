/**
 * fclists_lib.js — the FCLists loader primitive (the reusable, community-valuable core).
 * =====================================================================================
 *
 * Loaded on every desk page via `app_include_js` in hooks.py. It exposes ONE public helper:
 *
 *     fclists.extend_listview(doctype, extension)
 *
 * WHY THIS EXISTS (Finding A — the bug this primitive prevents)
 * ------------------------------------------------------------
 * Frappe concatenates the list-view JavaScript from EVERY installed app into a single bundle. They all
 * mutate the same global object: `frappe.listview_settings`. So if two apps both do
 *
 *     frappe.listview_settings["Item"] = { onload() { ... } };   // ❌ BARE REASSIGNMENT
 *
 * the SECOND file to load silently wins and throws away everything the first put there — including
 * ERPNext's own native list configuration for that doctype (its indicators, its buttons, its
 * `add_fields`, its `hide_name_column`, etc.). The list looks subtly broken and nobody knows why.
 *
 * The safe pattern is to *merge into* whatever is already there and to *chain* (not overwrite) the two
 * function hooks that matter — `onload` and `get_indicator` — so both the native handler and ours run.
 * `add_fields` must be *concatenated*, never replaced, so the columns each contributor needs are all
 * fetched. This helper encapsulates exactly that pattern so every FCLists `*_list.js` gets it right by
 * construction and no lane has to re-derive the merge-and-chain logic.
 *
 * USAGE (every FCLists *_list.js calls this — never a bare assignment):
 *
 *     fclists.extend_listview("Item", {
 *         add_fields: ["disabled", "item_group"],          // concatenated onto native + prior apps
 *         get_indicator(doc) {                             // runs FIRST; return undefined to fall
 *             if (cint(doc.disabled)) return [__("Disabled"), "gray", "disabled,=,1"];
 *             // returning nothing here => the previously-registered get_indicator is called (chained)
 *         },
 *         onload(listview) {                               // native/prior onload runs, THEN this
 *             listview.page.add_inner_button(__("Stock Board"), () =>
 *                 frappe.set_route("query-report", "FClist Item Stock"));
 *         },
 *     });
 *
 * Any other keys in `extension` (label, hide_name_column, button, formatters, …) are shallow-merged via
 * Object.assign, matching how a hand-written listview_settings object would behave.
 */
(function () {
	"use strict";

	// Namespace. frappe.provide is idempotent — safe if another FCLists asset already created it.
	frappe.provide("fclists");

	/**
	 * Safely extend the native (and any prior app's) listview_settings for `doctype`.
	 *
	 * @param {string} doctype   The doctype whose list view to extend, e.g. "Item".
	 * @param {object} extension The extra listview_settings to merge in. `onload` and `get_indicator`
	 *                           are CHAINED with any existing handler; `add_fields` is CONCATENATED;
	 *                           every other key is shallow-merged (Object.assign) and thus overrides.
	 * @returns {object} The resulting merged settings object (also stored on frappe.listview_settings).
	 */
	fclists.extend_listview = function (doctype, extension) {
		extension = extension || {};

		// Whatever is already registered — native ERPNext config and/or an earlier app's extension.
		var existing = frappe.listview_settings[doctype] || {};

		// Capture the handlers we intend to CHAIN, before Object.assign can overwrite them.
		var prior_onload = existing.onload;
		var prior_get_indicator = existing.get_indicator;
		var our_onload = extension.onload;
		var our_get_indicator = extension.get_indicator;

		// CONCAT add_fields (never drop columns another contributor needs).
		var merged_add_fields = (existing.add_fields || []).concat(extension.add_fields || []);

		// Shallow-merge everything else. `existing` first, then `extension` overrides scalar keys.
		// (onload / get_indicator here are placeholders we replace immediately below with the chained
		// wrappers, and add_fields is replaced with the concatenated array — so their order of assignment
		// does not matter.)
		var merged = Object.assign({}, existing, extension);

		merged.add_fields = merged_add_fields;

		// --- CHAIN get_indicator ---------------------------------------------------------------------
		// Our handler runs first; if it returns a truthy indicator we use it, otherwise we fall through
		// to the previously-registered handler. This lets an FCLists list add an indicator WITHOUT
		// hiding whatever ERPNext (or an earlier app) already decided for the other states.
		if (our_get_indicator || prior_get_indicator) {
			merged.get_indicator = function (doc) {
				if (our_get_indicator) {
					var result = our_get_indicator.call(this, doc);
					if (result) {
						return result;
					}
				}
				if (prior_get_indicator) {
					return prior_get_indicator.call(this, doc);
				}
				return undefined;
			};
		}

		// --- CHAIN onload ----------------------------------------------------------------------------
		// The previously-registered onload runs FIRST (so native buttons/filters are set up), THEN ours
		// (so our inner buttons are added on top). Neither is lost.
		if (our_onload || prior_onload) {
			merged.onload = function (listview) {
				if (prior_onload) {
					prior_onload.call(this, listview);
				}
				if (our_onload) {
					our_onload.call(this, listview);
				}
			};
		}

		frappe.listview_settings[doctype] = merged;
		return merged;
	};
})();
