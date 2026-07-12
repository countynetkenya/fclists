/**
 * fclists_periods.js — the QuickBooks-style "Report period" preset date filter for FCLists Script Reports.
 * ============================================================================================================
 *
 * Yokoten of fcreports/fcreports/periods.py (the FCDesk-Reports "Report period" dropdown) into FCLists'
 * OWN paradigm: FCLists has no server-rendered www page — its date filters live in Script Report `filters`
 * arrays (frappe.query_reports[...]), so the preset resolver lives here, client-side, composing the exact
 * client-side equivalents of the native `frappe.utils` primitives fcreports composes server-side.
 *
 * ANTI-REINVENTION (CLAUDE.md rule #1): we NEVER reimplement a calendar. Every preset composes native
 * `frappe.datetime` helpers (add_days, add_months, get_today) plus `moment(anchor).startOf/endOf(unit)` —
 * the SAME primitives frappe.datetime.week_start()/month_start()/quarter_start()/year_start() wrap
 * internally (those wrappers hardcode "now" with no anchor param, so last/next presets call moment
 * directly on a shifted anchor — not a re-derived calendar, just parameterising frappe's own wrapper).
 * moment's global week-start-day is configured by frappe on desk boot from the site's
 * `first_day_of_the_week` system default (frappe/public/js/frappe/desk.js `setup_moment()`), so
 * `.startOf("week")` here honours the SAME week boundary the server's `get_first_day_of_week` uses.
 *
 * The two FISCAL-anchored presets ("Next fiscal quarter" / "Next financial year") need
 * `erpnext.accounts.utils.get_fiscal_year`, which reads the Fiscal Year doctype — not available
 * client-side — so those two resolve via ONE whitelisted round-trip to fclists.periods.resolve_fiscal_period
 * (fclists/fclists/periods.py, FCLists' own thin copy of fcreports' `_fiscal()` — never a cross-app import).
 * Every other preset resolves synchronously, in-browser, with zero server round-trip.
 *
 * Community law (D-048/D-049): fclists stays required_apps=["erpnext"] — the shared thing is the native
 * util + the PATTERN, NOT a cross-app import; this file is FCLists' own thin copy (mirrors
 * fcreports/fcreports/periods.py's preset registry + bounds so the dropdown behaves identically app-to-app).
 *
 * PUBLIC API
 * ----------
 *   fclists.periods.PERIODS         — ordered [{key, label, group}, …] (display order; group == QBO section)
 *   fclists.periods.SELECT_OPTIONS  — PERIODS mapped to {value, label} for a Select filter's `options`
 *   fclists.periods.resolve(key)    — {from_date, to_date} 'YYYY-MM-DD' strings, sync; null for "custom",
 *                                      an unknown key, or a fiscal key (those need resolveFiscal, below)
 *   fclists.periods.resolveFiscal(key, company, callback) — async; callback(range | null)
 *   fclists.periods.apply(report, opts) — resolves the report's current "period" filter value and pushes
 *                                      the result onto opts.from_field/opts.to_field via
 *                                      report.set_filter_value() (the SAME mechanism erpnext's own reports,
 *                                      e.g. trial_balance.js, use to drive from_date/to_date off a dropdown)
 *   fclists.periods.filter_def(opts)   — a ready-to-splice Query Report filter dict: a "period" Select whose
 *                                      on_change calls apply(). opts: {from_field, to_field} (default
 *                                      "from_date"/"to_date" — every FCLists report with a date range uses
 *                                      those two fieldnames).
 *
 * USAGE — every FCLists report .js with from_date/to_date splices this ONE extra filter (placed right
 * before the From/To pair so it reads left-to-right as "pick a period, or type your own dates"):
 *
 *     frappe.query_reports["FClist Sales Invoice"] = {
 *         filters: [
 *             { fieldname: "company", ... },
 *             fclists.periods.filter_def(),
 *             { fieldname: "from_date", ... },
 *             { fieldname: "to_date", ... },
 *             ...
 *         ],
 *     };
 *
 * Picking anything other than "Custom" overwrites the From/To boxes (report.set_filter_value() triggers
 * the report to re-run once, same as typing a date by hand); "Custom" (the default) leaves them alone.
 */
(function () {
	"use strict";

	frappe.provide("fclists.periods");

	// Ordered preset registry — mirrors fcreports/fcreports/periods.py PERIODS verbatim (key/label/group)
	// so the dropdown reads identically whichever FCLists/FCDesk-Reports surface a user is on.
	fclists.periods.PERIODS = [
		// ── To date ──────────────────────────────────────────────────────────────────────────────────
		{ key: "today", label: "Today", group: "To date" },
		{ key: "this_week_to_date", label: "This week to date", group: "To date" },
		{ key: "this_month_to_date", label: "This month to date", group: "To date" },
		{ key: "this_quarter_to_date", label: "This quarter to date", group: "To date" },
		{ key: "this_year_to_date", label: "This year to date", group: "To date" },
		// ── Last ─────────────────────────────────────────────────────────────────────────────────────
		{ key: "last_7_days", label: "Last 7 days", group: "Last" },
		{ key: "last_30_days", label: "Last 30 days", group: "Last" },
		{ key: "last_90_days", label: "Last 90 days", group: "Last" },
		{ key: "last_week", label: "Last week", group: "Last" },
		{ key: "last_month", label: "Last month", group: "Last" },
		{ key: "last_quarter", label: "Last quarter", group: "Last" },
		{ key: "last_12_months", label: "Last 12 months", group: "Last" },
		{ key: "last_year", label: "Last year", group: "Last" },
		// ── Since ────────────────────────────────────────────────────────────────────────────────────
		{ key: "since_30_days_ago", label: "Since 30 days ago", group: "Since" },
		{ key: "since_60_days_ago", label: "Since 60 days ago", group: "Since" },
		{ key: "since_90_days_ago", label: "Since 90 days ago", group: "Since" },
		{ key: "since_365_days_ago", label: "Since 365 days ago", group: "Since" },
		// ── Next ─────────────────────────────────────────────────────────────────────────────────────
		{ key: "next_week", label: "Next week", group: "Next" },
		{ key: "next_4_weeks", label: "Next 4 weeks", group: "Next" },
		{ key: "next_month", label: "Next month", group: "Next" },
		{ key: "next_quarter", label: "Next quarter", group: "Next" },
		{ key: "next_fiscal_quarter", label: "Next fiscal quarter", group: "Next" },
		{ key: "next_year", label: "Next year", group: "Next" },
		{ key: "next_financial_year", label: "Next financial year", group: "Next" },
		// ── Custom (leave the manual From/To boxes alone) ───────────────────────────────────────────────
		{ key: "custom", label: "Custom", group: "Custom" },
	];

	fclists.periods.SELECT_OPTIONS = fclists.periods.PERIODS.map(function (p) {
		return { value: p.key, label: __(p.label) };
	});

	var FISCAL_KEYS = ["next_fiscal_quarter", "next_financial_year"];

	function _today() {
		return frappe.datetime.get_today(); // native — already 'YYYY-MM-DD'
	}

	function _fmt(m) {
		return m.format(frappe.defaultDateFormat); // explicit 'YYYY-MM-DD' — never rely on moment defaults
	}

	function _weekStart(d) {
		return _fmt(moment(d).startOf("week"));
	}
	function _weekEnd(d) {
		return _fmt(moment(d).endOf("week"));
	}
	function _monthStart(d) {
		return _fmt(moment(d).startOf("month"));
	}
	function _monthEnd(d) {
		return _fmt(moment(d).endOf("month"));
	}
	function _quarterStart(d) {
		return _fmt(moment(d).startOf("quarter"));
	}
	function _quarterEnd(d) {
		return _fmt(moment(d).endOf("quarter"));
	}
	function _yearStart(d) {
		return _fmt(moment(d).startOf("year"));
	}
	function _yearEnd(d) {
		return _fmt(moment(d).endOf("year"));
	}

	/**
	 * (from_date, to_date) 'YYYY-MM-DD' for a preset `key`, mirroring fcreports.periods.resolve_period's
	 * bounds EXACTLY (frappe.utils.get_timespan_date_range semantics — see that function's source for the
	 * authoritative definition of every "last"/"next"/"this" window). Returns null for "custom", an unknown
	 * key, or a FISCAL key (those resolve asynchronously via resolveFiscal(), below).
	 */
	fclists.periods.resolve = function (key) {
		if (!key || key === "custom" || FISCAL_KEYS.indexOf(key) !== -1) {
			return null;
		}
		var today = _today();

		switch (key) {
			case "today":
				return { from_date: today, to_date: today };

			// ── "… to date": native period START, capped at today ──────────────────────────────────
			case "this_week_to_date":
				return { from_date: _weekStart(today), to_date: today };
			case "this_month_to_date":
				return { from_date: _monthStart(today), to_date: today };
			case "this_quarter_to_date":
				return { from_date: _quarterStart(today), to_date: today };
			case "this_year_to_date":
				return { from_date: _yearStart(today), to_date: today };

			// ── Rolling "last N days" ────────────────────────────────────────────────────────────
			case "last_7_days":
				return { from_date: frappe.datetime.add_days(today, -7), to_date: today };
			case "last_30_days":
				return { from_date: frappe.datetime.add_days(today, -30), to_date: today };
			case "last_90_days":
				return { from_date: frappe.datetime.add_days(today, -90), to_date: today };

			// ── Whole "last" calendar periods ────────────────────────────────────────────────────
			case "last_week": {
				var lw = frappe.datetime.add_days(today, -7);
				return { from_date: _weekStart(lw), to_date: _weekEnd(lw) };
			}
			case "last_month": {
				var lm = frappe.datetime.add_months(today, -1);
				return { from_date: _monthStart(lm), to_date: _monthEnd(lm) };
			}
			case "last_quarter": {
				var lq = frappe.datetime.add_months(today, -3);
				return { from_date: _quarterStart(lq), to_date: _quarterEnd(lq) };
			}
			case "last_year": {
				var ly = _fmt(moment(today).subtract(1, "year"));
				return { from_date: _yearStart(ly), to_date: _yearEnd(ly) };
			}

			// ── "Since N days ago" — the util has no direct equivalent; native add_days only ────────
			case "last_12_months":
				return { from_date: frappe.datetime.add_months(today, -12), to_date: today };
			case "since_30_days_ago":
				return { from_date: frappe.datetime.add_days(today, -30), to_date: today };
			case "since_60_days_ago":
				return { from_date: frappe.datetime.add_days(today, -60), to_date: today };
			case "since_90_days_ago":
				return { from_date: frappe.datetime.add_days(today, -90), to_date: today };
			case "since_365_days_ago":
				return { from_date: frappe.datetime.add_days(today, -365), to_date: today };

			// ── "Next" calendar periods ───────────────────────────────────────────────────────────
			case "next_week": {
				var nw = frappe.datetime.add_days(today, 7);
				return { from_date: _weekStart(nw), to_date: _weekEnd(nw) };
			}
			case "next_4_weeks":
				// util has "next N days" but not "next 4 weeks" — native add_days only.
				return { from_date: today, to_date: frappe.datetime.add_days(today, 28) };
			case "next_month": {
				var nm = frappe.datetime.add_months(today, 1);
				return { from_date: _monthStart(nm), to_date: _monthEnd(nm) };
			}
			case "next_quarter": {
				var nq = frappe.datetime.add_months(today, 3);
				return { from_date: _quarterStart(nq), to_date: _quarterEnd(nq) };
			}
			case "next_year": {
				var ny = _fmt(moment(today).add(1, "year"));
				return { from_date: _yearStart(ny), to_date: _yearEnd(ny) };
			}

			default:
				return null; // defensive: a registry key with no resolver falls back to manual dates
		}
	};

	/**
	 * Async resolver for the two fiscal-anchored presets — ONE round-trip to FCLists' own whitelisted
	 * fclists.periods.resolve_fiscal_period (native erpnext.accounts.utils.get_fiscal_year anchor, with a
	 * calendar fallback server-side if no Fiscal Year is configured — the preset always resolves).
	 * `callback` receives {from_date, to_date} or null on failure.
	 */
	fclists.periods.resolveFiscal = function (key, company, callback) {
		if (FISCAL_KEYS.indexOf(key) === -1) {
			callback(null);
			return;
		}
		frappe.call({
			method: "fclists.periods.resolve_fiscal_period",
			args: { key: key, company: company },
			callback: function (r) {
				callback(r && r.message ? r.message : null);
			},
		});
	};

	/**
	 * Resolve the report's current "period" filter value and push {from_date, to_date} onto the report via
	 * report.set_filter_value() — the same mechanism erpnext's own reports (e.g. accounts/report/
	 * trial_balance/trial_balance.js) use to drive date filters off a dropdown. "Custom" (or no selection)
	 * leaves the manual From/To boxes untouched.
	 *
	 * @param {object} report  The Query Report instance (`this` inside a filter's on_change).
	 * @param {object} [opts]  {from_field, to_field} — defaults to "from_date"/"to_date".
	 */
	fclists.periods.apply = function (report, opts) {
		opts = opts || {};
		var from_field = opts.from_field || "from_date";
		var to_field = opts.to_field || "to_date";
		var key = report.get_filter_value("period");
		if (!key || key === "custom") {
			return;
		}

		if (FISCAL_KEYS.indexOf(key) !== -1) {
			var company = report.get_filter_value("company");
			fclists.periods.resolveFiscal(key, company, function (range) {
				if (!range) {
					return;
				}
				var upd = {};
				upd[from_field] = range.from_date;
				upd[to_field] = range.to_date;
				report.set_filter_value(upd);
			});
			return;
		}

		var range = fclists.periods.resolve(key);
		if (!range) {
			return;
		}
		var upd = {};
		upd[from_field] = range.from_date;
		upd[to_field] = range.to_date;
		report.set_filter_value(upd);
	};

	/**
	 * A ready-to-splice Query Report filter dict — a "Report period" Select whose on_change drives
	 * apply(). Every FCLists report with a date range calls this ONCE and places the result before its
	 * From/To filter pair.
	 *
	 * @param {object} [opts]  {from_field, to_field} — defaults to "from_date"/"to_date".
	 */
	fclists.periods.filter_def = function (opts) {
		opts = opts || {};
		return {
			fieldname: "period",
			label: __("Report Period"),
			fieldtype: "Select",
			options: fclists.periods.SELECT_OPTIONS,
			default: "custom",
			on_change: function (report) {
				fclists.periods.apply(report, opts);
			},
		};
	};
})();
