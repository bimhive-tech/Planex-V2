# Handoff — Cairo T3 Report Revisions (Planex V2)

Written 2026-09-15 by the "Planex Main" Claude session, to continue the work in
another session. It covers everything done since the planners' revision list for
the Cairo Airport T3 test report was turned into the **Cairo T3 Report
Revisions** plan, plus the three helper sessions that ran alongside it
(**Planex sub 1**, **Planex sub 2**, **Planex sub 3**).

Read sections 1–3 first. Section 4 is the item-by-item record, 5 covers the other
sessions, 6 lists what is still open, 7 is the technical reference and 8 the
gotchas that cost time.

---

## 1. Where things stand (one screen)

| Section | Items | State | Commit(s) |
|---|---|---|---|
| A · Data accuracy | A1–A8 | 7 done · **A5 on hold** (needs the invoice table's columns from the user) | `7a47644` |
| B · Report content | B1–B5 | 4 done · **B4 left as is** (user decision) | `32a6ca5` |
| C · Preview identical to the PDF | C1–C4 | **All done** | `56e7dc8` (C1–C3), `cf0d989` (C4) |
| D · Chart look and editing | D1–D4 | **All done** | `3a66e4c` |
| E · Schedule page | E1–E3 | E1, E2 **done** · **E3 not started** | `a261f09` |
| F · Source ledger | F1 | **Not started** | — |
| Side work (sub 1 + sub 3) | centring, figure order, zoom-stable text, fit-to-width canvas | Pushed, **not yet tested by the user** | `672e850` |

- `origin/main` = **`a261f09`** + this doc update. The working tree is clean (only `frontend/tsconfig.tsbuildinfo` shows as modified; it's a build artefact).
- Next in order: **E3 → F1**, with A5 whenever the user supplies the columns. (Updated after E1/E2 landed — see section 4 "E".)
- Plan page (live, private artifact, version 6): https://claude.ai/artifact/APw2m5pjjwJQVC1Wgp7Uwf. The local source was a scratchpad file of the Main session (`…/scratchpad/plan/cairo-report-revisions.html`). A new session should update the artifact through its URL (read it first, then publish with `url`).

---

## 2. Project and environment

| Thing | Value |
|---|---|
| Repo | `E:\Eng. Youssef Sami\Planex V2`, branch `main`, remote `https://github.com/bimhive-tech/Planex-V2.git` |
| Stack | Django/DRF backend in `backend/` (venv `backend/.venv`), Next.js App Router frontend in `frontend/`, PostgreSQL, CSS Modules only (see `CLAUDE.md` + `style.md`) |
| Dev servers | `.claude/launch.json`: `backend` = `backend/.venv/Scripts/python.exe backend/manage.py runserver --settings=config.settings.dev 8000`; `frontend` = `npm --prefix frontend run dev` on 3000. Start them with the Browser pane's `preview_start`, never with Bash. |
| Browser pane | The app needs the **user** to sign in. The agent must never enter credentials. Sessions expire (401 → sign-in page): ask the user to sign in again. The signed-in account is "Super Admin", which **cannot** open the MCG Cairo report `5a77cd93…` ("No Report matches"). |
| Type check | `cd frontend && npx tsc --noEmit` (≈1–4 min). Pipe `< /dev/null`. |
| Backend tests | `cd backend && .venv/Scripts/python.exe manage.py test apps.reports --noinput` (~420 tests, 8–10 min). The DB is the shared remote `test_railway`: **run one suite at a time**. A dropped connection is a flake: rerun that class. "Database being accessed by other users" can give a false exit 0: read the log. |
| Commits | End messages with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. The user wants a commit + push after each section, and replies as a status table (done / not done + why / next). |

### Data used for the Cairo work

| Report id | Project | Notes |
|---|---|---|
| `68679aa5-a236-4412-9fff-e1cbeae78041` | Admin Cairo project `0f8af361…` (توسعة وتطوير مبنى الركاب صالة (3) - مطار القاهرة) | The report used for C4/D verification in the Browser pane. No submittal data. 20 PDF pages, 16 layout pages + 4 continuation pages. |
| `5a77cd93-dc4e-4a24-a5aa-ac5e8eae1738` | MCG Cairo project `f1cb52ad…` | Has the dashboard panels (duration, submittals grid, BOQ, progress, tracking). Used for chart renders from the shell. |
| `13a228b8-585b-4bf8-b5c8-e46463e5e90b` | Mansoura 6 (report "(53)") | Used by sub 1. Building its context takes ~14 min against the remote DB. |
| `e360498f…` | Saint Catherine | 7,045 shop drawings + 432 material submittals as rows; its context build is too slow for quick scripts. |

Source files the planners use (in the user's Downloads): `P6 templete - Cairo Airport Terminal 3.xlsx` (the importer reads sheet 1 **`p6`**; `Planex Code` is the legend; `Sheet1`, `القديم`, `الجديد` are not read) and the dashboard workbook dated 02-08-2026.

---

## 3. Timeline and commits

| Commit | What |
|---|---|
| `e3f9812` | (before the plan) Size-aware chart axes (`pdf_axes.py`) and the dashboard's own panels, planner items F1–F7. Merged fast-forward at the start of this stretch. |
| `4368b2f` | (before the plan) 7-item round: summary table stable under zoom, every chart resizable, F2 = the dashboard's 3-slice progress pie, F3 placed in the report, F5 percent/money switch (default percent), full per-chart colour and text control (`ChartStyleBlock`). |
| `7a47644` | **Register A**: every figure is the one its source states. |
| `32a6ca5` | **Register B**: page 4 folds into the summary, chart 9 and chart 15 removed. |
| `56e7dc8` | **C1–C3**: Arabic chart text reads correctly on the canvas, browser font names, description shown and RTL wrap fixed in the PDF. |
| `cf0d989` | **C4**: every page of the Customize canvas matches the PDF. |
| `672e850` | **Sub 1 + sub 3** (committed by sub 1 at the user's request): centred tables/pies, figures numbered in reading order, zoom-stable text (`FixedZoom`), canvas fit-to-width + slimmer side columns (`useFitZoom`). |
| `3a66e4c` | **Register D**: D1–D4. |
| `31dafd8` | This handoff document. |
| `a261f09` | **E1 + E2**: one Import dialog; Planex-code tree, report reads through empty levels. |

### The user's original list (the "your #N" on the plan page)

| # | Request (paraphrased) | Item |
|---|---|---|
| 1 | Charts 3/4 (submittals) compressed; check all charts | D1 |
| 2 | Every chart fully modifiable | D2 |
| 3 | Resizing UX | D3 |
| 4 | Where charts 7 and 8 come from | A8 |
| 5 | Remove chart 9 | B1 |
| 6 | Rounding sweep | A2 |
| 7 | Chart 10 financial progress wrong (should come from مقارنة المستخلصات) | A1 |
| 8 | Page 4 becomes part of الملخص | B2 |
| 9 | Customize preview identical to the PDF | C1–C4 |
| 10 | Text box formatting controls on the right | D4 |
| 11 | Schedule "Import" button with a dialog (date, P6 or dashboard), next to Export P6 | E1 |
| 12 | Data source list, page by page | F1 |
| 13 | Page 6 description missing in the preview | C3 |
| 14 | Chart 13 source | A6 |
| 15 | Remove chart 15 | B3 |
| 16 | Chart 16 is the same as 13 | A6 |
| 17 | المسار الحرج source | A4 |
| 18 | Chart 20 y-axis to 100% | A7 |
| 19 | موقف المستخلصات full review | A5 |
| 20 | Schedule tree must follow the Planex Code (skip rows 1–2; Area › Sub-area › … › Sub-discipline with "No X" placeholders); overlapping rows in the right panel | E2, E3 |
| 21 | Review نسب الإنجاز | A3 |

### Decisions the user made

- **A1:** where P6 and the dashboard both state a figure, **P6 wins**.
- **A2:** percentages to **2 decimals**, money **in full** (to the cent, never K/M/B).
- **A5:** on hold.
- **A6:** remove chart 13; chart 16 becomes the dashboard's "DURATION (Working Days)" pie.
- **B2:** keep the charts' size and move them up.
- **B3:** rational space use: no big gaps, but don't widen charts unless needed.
- **B4:** keep the empty المعوقات page as is.
- **C4:** fix element by element (not a rendered-PDF underlay).
- **D3:** smooth drag + instant redraw (not fixed text size, layout steps or presets).
- **E2:** every empty Planex-code level is its own row (not folded).
- Only commit/push per section; sub 1's work stays for the user to test (then it was committed anyway at the user's "commit everything" request).

---

## 4. Item-by-item record

### A · Data accuracy (`7a47644`)

Rule: every value comes from P6, the dashboard workbook, or a field entered on the project; anything Planex calculates says how; no estimate prints as a source figure.

- **A1 — Financial progress in chart 10 equalled physical progress.** It was P6 earned value ÷ budgeted cost, which on this file is % complete × budget, so it could never differ.
  - The Planex-code importer now reads the P6 **title row** (`ScheduleRoots.stated_progress`: Performance % 0.5955, Schedule % 0.9445). `project_overall_progress` prefers the stated figure when there's no as-of override and the batch is the latest. `_planned_progress(current=True)` prefers `imported_planned_progress_percent`.
  - Chart 10 = 94.45% / 59.55% / **51.28% (08/07/2026)**, from Dashboard!W21 "Actual Invo. (C.D 08/07/2026)", parsed by `dashboard_panels.parse_progress`. The date is appended to the bar name.
  - Chart 11's previous month now comes from the dashboard's previous-month column (`parse_tracking`, 59.38 / 59.38), not a copy of the current month.
  - The stated percentages were backfilled for Cairo (59.55 / 94.45) and Mansoura (88.06 / 100.00) from their own P6 files. The Cairo dashboard panels were refreshed on the MCG project.
- **A2 — Rounding sweep.** Every rounding step was removed from chart and table data. `_pct_label` / `_money_label` / `_count_label` in `pdf_charts.py`, `format_money(value, currency, decimals=2)`, new `format_quantity`, and `number_format` in `pdf_axes.py` always writes full amounts. The area prints 3,424.31 m². Upright bar labels (with a shorter plot) when "100.00%" is too wide for a bar.
- **A3 — Every zone's planned % was the project's 94.46%.** Zones now get `scope_planned_map` = the planned-cost map merged over a per-scope weight-based Schedule % fallback (`_scope_planned_by_weight`): Part 2 - Level 2A 62.25%, Part 2 - Mezanine 91.13%, the rest 100.00%. Walk way (no budget) falls back to its activity's own 100%. السابق stays "—" because no earlier progress record exists.
- **A4 — Critical path delays used Planex guesses.** P6 has no baseline finish per zone, so the table (`_critical_path_rows`) now prints Start (MIN), Finish (MAX), Total Float (MIN) per zone from P6 activities. Columns `col_zone/col_start/col_finish/col_total_float` ("الفائض الكلي (يوم)"). Sub 2 verified all 9 rows against the Excel (section 5).
- **A5 — Invoice status page (on hold).** 19 rows, value empty on 18. The only value, مستخلص جاري (28) = 332,945,520.59 EGP, is also the total. Row names are column headings of مقارنة مستخلصات. The invoice-status chart draws nothing. **Needed from the user:** the table's columns (e.g. extract no., period to, gross works, deductions, net this extract, cumulative, % of contract). Then walk the sheet with them and rebuild the importer, table and chart.
- **A6 — Duration charts.** Chart 13 (المدة الزمنية) was removed. `project_duration` became the dashboard pie: slices total 1,380 / elapsed 1,313 / remaining 67 from Dashboard!W15:W17, palette[0..2], legend underneath. Migrations `0013_dashboard_duration_charts` and `0014_duration_pie_replaces_two_charts` (the pie takes the old chart's box, `chart_type` pie). `layout_seed._dashboard_page` seeds it for new templates.
- **A7 — BOQ axis stopped at 32%.** In percent mode the axis runs 0–100 (`boq_financial_progress_chart(value_mode)`). The three missing budget bars are the dashboard's own zeros (W119:Z119).
- **A8 — Charts 7 and 8 sources, confirmed from the Excel.** Sheet `p6`. Bar = Σ(Activity % Complete × Budgeted Total Cost) ÷ Σ Budgeted Total Cost, and planned the same with Schedule % Complete. Chart 7 groups by Planex Code Part+Level (e.g. Part 2 - Level 2A: 65 activities, rows 104–466 → 45.45% actual / 62.25% planned). Chart 8 groups by discipline (Civil 100/100 · Arch 29.20/97.87 · MEP 50.14/88.76 · Elevators 66.64/100 · Landscape 27.85/84.39 · Cladding 99.44/100).
- Tests: `backend/apps/reports/test_register_a.py`, `projects/test_dashboard_panels.py`, and updated `tests.py` (money `.00`, stated-figure tests, the old CriticalPathRowsTests removed).

### B · Report content (`32a6ca5`)

- **B1** Chart 9 (full-width progress by area) removed from both Arabic templates and all four saved reports.
- **B2** Page 4 → **الملخص (3)**, headed الملخص; the charts keep their size and move to the top.
- **B3** Chart 15 (time performance) removed from تقدم المشروع. zone_progress moves up under the gauge and widens to the right edge only because there was an empty quarter; its bottom edge is kept.
- **B4** المعوقات prints only its heading (no delays recorded). Left as is.
- **B5** The dashboard's `progress curve` row 6 "Late Budget Cost" is blank, so late planned is 0 every month. A series that is zero/None in every month is no longer drawn.
- Migrations: `0011_wording_on_saved_reports` (fixes 0009, which read report layouts at the wrong nesting: overrides keep pages under `layout_override["layout"]["pages"]`), `0012_summary_over_two_pages`, `0015_register_b_report_content` (`_fold_area_page`, `_drop_time_performance`). Data migrations must be idempotent and irreversible.
- Tests: `test_register_b.py`.

### C · Preview identical to the PDF (`56e7dc8`, `cf0d989`)

- **C1** Chart text is already shaped + bidi-reordered for the PDF (`pdf_base.shape`), and the browser reversed it again. `svg_export.drawing_to_canvas_svg` prepends `direction: ltr; unicode-bidi: bidi-override` to every `<text>`.
- **C2** PDF font names (`Amiri-Bold`, `Helvetica-Bold`, `Times-Roman`) are mapped to CSS family + weight in `svg_export._FONTS`.
- **C3** The canvas description shows `effectiveDescriptionHtml` (element html → report narrative → project description), mirroring `pdf_canvas._effective_description_html`. In the PDF, a wrapped RTL paragraph now breaks **before** shaping (`richtext._wrap_rtl_runs`, `_line_para(max_width)`), so its first line prints first.
- **C4** All 20 pages were compared (canvas clone overlay vs PDF page images) and every difference fixed:
  - **Info table:** bold heading-colour labels on the right (`dir="rtl"` on the table), no bullet/grey fill, values right-aligned under RTL, the PDF's 50 mm label column (`pdf_tables.INFO_LABEL_COL_MM`, `TABLE_COL_WIDTHS_MM["project_info"]`). The column drag is mirrored for RTL.
  - **Tables:** style from the backend (`_canvas_table_style`: text colour, label colour, line spacing, rtl). Per-kind padding/grid (info 8pt / 0.7pt, data 6pt / 0.6pt). Border floored at 0.5px, and side padding gives back the border width. The row "×" and row grip are overlaid in the first cell (`RowControls`); the column "×" is overlaid on the header corner. Both used to take width and made columns narrower than the PDF.
  - **Numbered captions** ("جدول 3 - …"), **field values** as the PDF resolves them ("يوليو 2026") and the **description text style**, all from `toc_entries` (`captions`, `field_values`, `description_style`). The `useTocEntries` fetch now runs whenever captions/fields/descriptions exist.
  - **Charts:** every `<clipPath id="clip">` was shared across SVGs on one page, so charts after the first were clipped to the first's size (p7 chart 10). Ids are now unique per drawing, and the clip is dropped (the PDF never clips, so labels just outside the box, like the pie's "77", show). No-data charts show no placeholder, title or caption unless hovered/selected.
  - **Split tables:** `table_overflow` returns `first_rows`, and `firstChunkTableData` cuts the page's table to the rows the PDF prints there.
  - **Shapes:** fill/stroke only when set, line default black 0.5 (the cover's maroon bars had a navy outline).
  - **Canvas actions** (`_canvas_inputs` in `views.py`) register fonts and set `ctx["arabic"]` like `build_canvas_pdf`. Before, a fresh process 500'd on an unregistered font, and tables came back LTR.
  - **OverflowClip** measures a `.tableClipContent` wrapper, not the box with its note. The note deciding its own visibility caused an infinite render loop once sub 1 centred tables.
  - Known small differences: p6 description breaks one word later than the PDF (browser vs reportlab metrics); the "Curtin wall" header is one line on the canvas, two in the PDF.
  - Tests: `test_register_c.py` (SVG text/fonts/ids, RTL wrap, toc-entries additions, table style, first_rows, info column fraction). `tests.CanvasColumnWidthParityTests` now covers project_info.
  - C4 was committed by building the git index directly (`hash-object` + `update-index`) so sub 1's uncommitted hunks in the same files stayed out, then testing the staged tree in a separate checkout.

### D · Chart look and editing (`3a66e4c`)

- **D1 — room for every chart's text.**
  - `submittals_breakdown_chart`: value-axis numbers get their own band (`axis_h`); they used to fall below the drawing, so the axis had ticks but no numbers. The side legend is sized to its longest name (`legend_w = text + 20`) and only kept when the bars keep ≥70% of the plot width; otherwise it wraps under the chart.
  - `_reference_pie`: room above/below for outside value labels (`label_room = popout + 1.2·font + 2`, pie ≤ (h − legend − 2·room)/1.15). The duration pie's "67" was cut off.
  - Legend swatches have no black outline.
  - Sweep: 18 Cairo charts rendered at their placed sizes (shell script → renderPDF → PyMuPDF PNG → contact sheet); nothing else cramped.
- **D2 — chart controls.** New Properties block `ChartLayoutBlock.tsx` ("Axes, bars and legend"). Props are read by the backend:
  - `axis_min`, `axis_max`, `axis_step` → `pdf_axes.AXIS_OVERRIDE` contextvar, applied inside `percent_axis`, `number_axis` and `horizontal_number_axis` (`_overridden`; a non-rising range or >200 ticks is ignored). The s-curve and cash-flow callouts use the real axis range.
  - `bar_gap` (Excel gap width 0–500, smaller = thicker) and `series_gap` (0–100) → `_bar_geometry`.
  - `line_width` → `_line_width(default)` in the s-curve / cash flow / cash-flow curve.
  - `decimals` (0–2) → `_decimals()` used by `_pct_label`, `_money_label`, time-performance and progress pie formats. `freeze_formats(drawing)` binds bar-label formatters to the element's options, because reportlab calls them at draw time, after `chart_options` has exited.
  - `legend_position` (top/bottom) → `apply_legend_position`: legends are `_LegendGroup`s; a legend band above/below everything else swaps with the rest of the chart. Side legends are left alone.
  - Gauge: `gauge_low/mid/high/max` + `color_gauge_bad/warn/good/excellent` → `chart_style_override._gauge_override` (both `gauge_thresholds` and `spi_thresholds`; out-of-order bands ignored). Shown only for gauge charts (`isGaugeChart`).
  - Submittal palette pickers are labelled by discipline: `pdf_canvas.chart_series_names` → `chart-svgs` returns `series`, and `LayoutEditor.selectedChartSeries` passes it to `ChartStyleBlock`.
  - Reset clears all of these (`CHART_STYLE_PROPS`).
- **D3 — smooth resize.** `useChartSvgs` rewritten: first load draws everything (800 ms debounce). After that it compares per-chart signatures (w, h, props, page repeat; not x/y) and requests only touched charts with `only: [...]` after 120 ms, merging results and discarding responses overtaken by a newer edit. Moving a chart no longer redraws it. `chart-svgs` returns each chart's drawn `w`/`h`. While `live.w/h` ≠ the element's size, `ChartPreview` shows the old SVG fitted and centred (`preserveAspectRatio xMidYMid`), dimmed, with a spinner (`.chartSvgStale`, `.chartRedrawing`). Measured: ~38 KB request vs 324 KB, redraw ~1.5 s after release.
- **D4 — toolbar in the right panel.** `RichTextEditor` takes `toolbarTarget` and portals its toolbar there. `TextToolbarSlot.tsx` (context) is provided by `LayoutEditor` and rendered by `ElementInspector` for a description. `DescriptionPreview` passes the slot and treats clicks inside it as inside the editor. The edit overlay is exactly the box (`[data-toolbar-aside="on"]`).
- Tests: `test_register_d.py` (axis room, bar share, long names, pie bounds, axis override, invalid axis, bar gap, decimals, legend top, gauge bands, series names, `only` + size). Test helpers in `test_dashboard_charts._texts` and `tests.SubmittalsChartLegendTests` now look inside groups. A resolver test compares the bound formatter's output. The full suite ran 417 tests with one failure (that identity check), which was fixed and its class rerun green.
- Verified in the Browser pane on report `68679aa5`: axis max 120% (ticks to 120%), stale drag state captured then redrawn, undo restored the element, toolbar rendered in the inspector with 11 controls, pressing it kept editing, clicking outside ended it, no console errors on a fresh load.

### E · Schedule page (E1, E2)

- **E1 — one Import dialog.** `ProjectImportButton` + `ProjectImportDialog` (`frontend/src/components/features/projects/`, text and result wording in `lib/projectImport.ts`). "Import" sits beside "Export P6" in the project top bar (`ProjectWorkspace.tsx`). It offers P6 schedule if the user can manage the project and Dashboard workbook if they can manage finances, then asks for the "Data as of" date and the file. The schedule goes to `/upload/import/<project>` with `date`, the dashboard to `/api/projects/<id>/dashboard/import/` with `date`. After an import the Schedule/Finances tab remounts (`key={importKey}`). The old "Import Excel" button + date box were removed from `ProjectSchedule.tsx`; `DashboardImport.tsx` was deleted and the Finances Imports view opens the same dialog. Backend: `DashboardImport.data_date` (migration `projects/0058_dashboardimport_data_date`, **already applied to the shared dev DB**), set from `date` or the filename (`imports.parse_date_from_name`), listed in the history ("Data as of"). New `upload` icon.
- **E2 — Planex-code tree.** The importer already built the strict chain since `47ff0d6` (every legend slot is a level; empty slots are `is_placeholder` scopes named "0"). What E2 added:
  - Wording: an empty PH slot reads **"No phase"** (the legend's word), while the scope type stays `stage` (`ProjectScope._PLACEHOLDER_LEVEL_WORD`, `level_name` property → serializer → tree badge; `enum_no_phase` label).
  - **Report reads through empty levels** (`apps/reports/scope_tree.py` `ScopeTree`: `real_children`, `real_ancestor`, DFS `order`). Used in `services._zone_rows`, `_hierarchy_rows`, `_phase_rows`, `_discipline_rows` (`phase_of` walks past an empty sub-discipline), `_gantt_rows`, `_work_rows` (no "0" trade), and `_disambiguated_names` (prefix = nearest real ancestor, so "Part 1 - Level 2", not "0 - Level 2").
  - Both Cairo schedules had been imported (8 and 13 Sep) **before** `47ff0d6`. The **Admin Cairo test project (`0f8af361…`) was re-imported** through the real endpoint from its stored workbook with the same data date (new batch `e83b27d8…`, the old batch `1c461f0e…` is kept and can be deleted in the picker): 492 activities, 59.55% / 94.45%, 154 scopes. A before/after snapshot of report `68679aa5` showed zones, hierarchy, areas, critical path, overall, planned, SPI identical; the discipline table's 288 values identical with rows/columns in tree order; the trades chart order changed (Civil, MEP, Elevators, Facade, Landscape, Architectural — the tree's order). **The MCG Cairo project (`f1cb52ad…`) still has its old tree** until someone re-imports it.
  - Tests: `apps/projects/test_register_e.py` (chain order and "No …" names, root is "No area", a part-less row still passes all 9 levels, report rows never an empty level and named by Part, dashboard data date recorded/listed/from filename/refused when malformed). Borrowing `LegendReadImportTests`' workbook by attribute (importing the class into the module would run its tests twice).
  - Known: at phone width the 9-level indentation pushes names off-screen (desktop fits) — part of E3.

---

## 5. The other sessions

### Planex sub 1 (named `planex-v2-a2`, later `planex-v2-57`)

- **Request:** tables on pages 12–13 not centred, and spare page space should sit evenly around content; page 6 Arabic text re-wraps when zooming the canvas; figure numbering must be in order.
- **Done (pushed in `672e850`):**
  - `pdf_tables.centred_offset`, and `draw_table_in_box` centres and returns the drawn height. `_draw_table_element` centres chunk0 and continuation chunks, with title/caption hugging the table.
  - `_reference_pie` drawing height = pie + legend, and `_draw_chart_element` centres short drawings (canvas: `.captionedBox:has(.chartSvgLive)`, `CaptionedBox centred`).
  - `pdf_canvas.reading_order`: captions numbered row by row, right-to-left in Arabic (verified on report 53 page 9: donut 1, gauge 2, lower row RTL; figures 1–68, tables 1–22).
  - `FixedZoom` in `ElementPreview.tsx`: text/field/table/toc lay out at 96/25.4 px/mm and are CSS-scaled, so line breaks don't change with zoom. The description is excluded. The TableSizing grips convert with the on-screen size.
  - Two tests in `tests.CanvasPdfTests`, and a `REPORT_BUILDER_FEEDBACK.md` entry dated 2026-09-15.
- **Not done:** page-level re-centring of authored positions (it would fight manual placement).
- **User to test:** report (53): p6 zoom in/out keeps line breaks; pp12–13 unit table and duration pie centred with captions under them; PDF caption numbers in order.
- At the user's request ("commit and push everything"), sub 1 committed all sessions' changes as `672e850` and wrote a progress report on the plan (which was then correct: A/B/C done, D/E/F not started).

### Planex sub 2 (analysis only, no code changes)

- **Q: where does page 8 (المسار الحرج للتأخيرات) come from?** All from the P6 Excel sheet `p6`: column B PLANEX CODE (zone = Part + Level), J Start → MIN, K Finish → MAX, L Total Float → MIN. Built by `services._critical_path_rows`, drawn in `pdf_canvas`. The import used is the one pinned on the report, else the latest on or before the report date. "planned_start/planned_finish" on `Activity` hold P6's *current* Start/Finish, not a baseline.
- **Verification:** الفائض الكلي (يوم) is P6 Total Float in days. All 9 rows matched the Excel exactly (e.g. Level 2 −16, Part 1 - Level 2A −2, Part 2 - Level 2A −47, Part 2 - Mezanine −25). No overrides or hidden rows. Both Cairo reports agree.
- **How to check by hand:** filter column B with *Contains* `-P2-0-L.2A-` (use the full text), then MIN(J)/MAX(K)/MIN(L). Start dates ending in " A" are text, so Excel's MIN skips them.
- **Open finding:** **121 activities have no Level** (9th code part `0`) and appear on no zone row: 66 Civil, 29 MEP, 3 Elevators, 2 Landscape, 4 Cladding, 16 façade (`EF/NF/SF`). Four have negative float, including **row 636 Testing and Commissioning −47**, and rows 630/631/634 at −20. Suggested: a "General / غير مخصص" row (or one per façade). **Waiting on the user.**
- Risks it listed: float exported in hours (≈8× too big), decimal float truncated not rounded, WBS summary float can differ from MIN of activities, blank float on completed activities, manual overrides, a pinned older import.

### Planex sub 3 (named `planex-v2-42`, the "ca" session)

- **Request:** on smaller screens the Customize preview is too small and the side columns too wide.
- **Done (pushed in `672e850`):** `frontend/src/hooks/useFitZoom.ts` starts the zoom at the largest that fits the canvas width (never above 100% automatically; manual zoom sticks, re-fits on resize/orientation change). Slimmer columns at 1024–1439px (left 320→270px, Properties 250→230px, tighter gaps/padding). ≥1440px unchanged.
- **Not verified in a browser** (a second dev server would hit CORS). **User to test:** a landscape page on a laptop screen fits with no sideways scroll; if page names in the left list get cut off, hide row buttons until hover.

### Coordination lessons

- All four sessions share **one working tree**. Before editing shared files, message the other sessions (`SendMessage` to their `uds:` address), and never `checkout` / `stash` / `reset` files another session touched.
- To commit only your own hunks from shared files: build the staged content (`git show HEAD:file` + your edits), `git hash-object -w --stdin --path <file>` + `git update-index --cacheinfo`, then `git checkout-index -a --prefix=<tmp>/`. Test that tree (junction `node_modules`, run tsc + the reports suite) before committing.
- Another session's backend edits restart runserver mid-request (canvas shows "Couldn't load…"). Reload the page.
- The user said every session should stop other work until the Cairo T3 Report Revisions are finished.

---

## 6. Open items and decisions

| Item | What's needed |
|---|---|
| ~~E1~~ ~~E2~~ | Done (section 4 "E"). The MCG Cairo project needs a re-import to get the new tree; the user should re-check the trades chart order. |
| **E3** Right-hand panel rows overlap on the schedule page; also the 9-level tree indentation at phone width. | Reproduce at desktop/tablet/phone widths, fix, re-check. |
| **F1** Source ledger: per page and per element, what it shows, where each value comes from (P6 column / dashboard cell / project field), any Planex formula, estimates flagged. First as a document for this report, then a source line on each chart/table in the editor. Much of the tracing is already in A1–A8 and sub 2's findings. | Not started. |
| **A5** Invoice status rebuild. | The table's columns from the user. |
| Sub 2's 121 level-less activities (Testing & Commissioning −47). | User decision: add a General row? |
| Sub 1 and sub 3 changes. | User to test (see section 5). |
| C4 leftovers: p6 description wraps one word later; "Curtin wall" header one line vs two. | Minor. Not rechecked since `FixedZoom`. |
| D2 note: an axis max below the data lets bars run past the plot (reportlab doesn't clip), and then a top/bottom legend swap is refused because the bars reach the legend band. | Acceptable for now; could clamp. |
| `chart-svgs` on a repeating page returns the last instance's drawing per element id (unchanged behaviour). | FYI. |
| Plan page | Update E/F as they progress (artifact URL above). |

---

## 7. Technical reference

### Report rendering pipeline

- `services.build_report_context(report)` → `ctx` (project, zones, duration, dashboard panels, submittals, cash flow, …). `views._cached_report_context` caches it per report. It hands back a fresh copy per request, and `_will_draw_cache` lives in a process-local store.
- Config: `constants.merged_config(template.config)`, then `merge_layout_override(cfg, report.layout_override)`. Templates keep pages under `config["layout"]["pages"]`, reports under `layout_override["layout"]["pages"]`.
- PDF: `pdf_canvas.build_canvas_pdf` → `expand_pages` (repeating pages) → `_expand_table_overflow` → `_collect_captions` (numbering, now in `reading_order`) → draw per element type.
- Charts: `pdf_canvas.resolve_chart(source, chart_type, cfg, ctx, scope, w, h, scope_zone_id, props)` wraps `_resolve_chart` in `pdf_charts.chart_options(props)` (contextvars: font scale via `pt()`, legend, values, bar/series gap, line width, decimals, plus `pdf_axes.AXIS_OVERRIDE`) and `chart_style_override(cfg, props)` (colours, palette, text labels, gauge). It then calls `freeze_formats`, `hide_values` and `apply_legend_position`. The PDF, the has-content check, the canvas SVG and rich-text embeds all go through it.
- `chart_box_content(props, cfg, h)` gives the chart's height after title/caption strips; the same numbers are used by the PDF and the canvas.
- Arabic: `pdf_base.shape` (arabic_reshaper + python-bidi, display order). Wrap before shaping (`pdf_tables._wrap_shape`, `richtext._wrap_rtl_runs`).
- P6 import: `projects/p6_id_schedule_import.parse_id_schedule_sheets` (Planex Code format; `ScheduleRoots.stated_progress`), `p6_schedule_import.build_from_p6_schedule(..., stated_progress)`, `imports.py`. Dashboard: `projects/dashboard_panels.py` (duration, submittals, boq, progress, tracking) → `DashboardPanels` model (migration `0057_dashboard_panels`).

### Canvas (Customize tab) endpoints — `backend/apps/reports/views.py`

All take `{"layout_override": {"layout": {"pages": …}, "page_design": {"master_elements": …}}}` and go through `_canvas_inputs` (fonts + direction). Frontend calls them through Next routes `frontend/src/app/reports/[id]/*-file/route.ts`.

| Endpoint | Returns | Frontend hook |
|---|---|---|
| `chart-svgs` (+ optional `only: [ids]`) | `{charts: {id: {status, svg, w, h, series?}}, labels, colors}` | `hooks/useChartSvgs.ts` |
| `table-data` | `{tables: {id: {status, kind, header, rows, style, col_widths, …}}, labels}` (`style` from `_canvas_table_style`) | `useTableData` |
| `table-overflow` | `{continuations: {id: [chunks]}, first_rows: {id: n}}` | `useTableOverflow` → `lib/reportOverflow.ts` |
| `toc-entries` | `{tables, figures, images, captions, field_values, description_style}` | `useTocEntries` |

Frontend canvas files: `components/features/reports/ReportLayoutEditor.tsx` → `designer/ReportConfigurator.tsx` → `designer/LayoutEditor.tsx` (canvas + `ElementInspector`). Previews live in `designer/ElementPreview.tsx` (`ElementPreview` → `FixedZoom` / `ElementBody`, `ChartPreview`, `TablePreview`/`LiveTableBody`, `DescriptionPreview`, `CaptionedBox`, `OverflowClip`). Also `TableSizing.tsx`, `ChartStyleBlock.tsx`, `ChartLayoutBlock.tsx`, `TextToolbarSlot.tsx`, `designer.module.css`, `lib/reportElements.ts` (sources, chart props), `lib/reportLayout.ts` (types).

### Useful scripts (recreate in a scratchpad)

- **Render a report's PDF pages:** Django shell → `from apps.reports.views import _render_report_pdf`; `data, _ = _render_report_pdf(report, None)`; PyMuPDF `fitz.open(stream=data)` → `page.get_pixmap(dpi=80).save(...)`.
- **Render every chart at its placed size:** iterate `expand_pages`; for each chart element `chart_box_content` → `resolve_chart(...)` → `renderPDF.drawToString(drawing)` → PyMuPDF PNG. `renderPM` is **not** available (no rlPyCairo). Tile PNGs with PIL into a contact sheet.
- **Canvas vs PDF comparison in the Browser pane:** clone `[class*="designer_paper__"]` into a fixed overlay scaled to fit (optionally a region), then screenshot. The pane is small (~454×404), so view quadrants. Wait a couple of animation frames before screenshotting, or you get the previous frame. Click pages via `[class*="designer_pageRow__"] [class*="designer_pageRowMain"]`.
- Run shell scripts with `manage.py shell -c "exec(open(r'path', encoding='utf-8').read())"` and `PYTHONIOENCODING=utf-8` (the Windows console codepage breaks Arabic prints).

---

## 8. Gotchas that cost time

- **Bash heredocs** containing backticks/quotes sometimes fail ("unexpected EOF while looking for matching `'`"). Write patch scripts with the Write tool, then run them.
- `cat > file` with no input **hangs** the Bash tool (it waits on stdin).
- Pass `< /dev/null` to `npx tsc` and `manage.py test` so they can't wait on stdin.
- String-replace patches: assert each target occurs exactly once. Files shared with other sessions change under you, so re-read before editing.
- Tests that inspect `drawing.contents` for Strings or shapes must recurse: legends are now `_LegendGroup`s.
- reportlab calls bar-label formatters at **draw** time: anything read from contextvars must be bound first (`freeze_formats`).
- Every reportlab SVG uses the same `id="clip"`: on one HTML page they collide (fixed in `svg_export`).
- A component that sets state from a measurement which its own output changes will loop (the OverflowClip bug).
- Next.js HMR can leave transient "X is not defined" errors in the console buffer from half-applied edits. Judge on a fresh reload.
- The user's session in the Browser pane expires. When `/api/...` returns 401 and the sign-in page shows, ask the user to sign in.
- Git on Windows prints LF→CRLF warnings; harmless. `frontend/tsconfig.tsbuildinfo` changes on every type check: don't commit it unless intended.
