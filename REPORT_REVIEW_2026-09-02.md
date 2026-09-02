# Report Review — 2026-09-02

Client feedback on the exported PDF, broken into one item per issue so we can work
through them **one at a time**. Nothing here is fixed yet.

Each item records the client's own words first, then what I understood from them.
Where I already know the answer (the "why" questions), it's under **Answer**.

> **On the images:** the screenshots pasted into chat can't be written to disk from
> here. Where a screenshot was a page of *our* report, `docs/review-2026-09-02/`
> holds that same page regenerated from the current build — the client's page
> numbers are one lower than the current build's, because pagination shifted after
> the bar-width and table changes. Where a screenshot was the client's Excel, the
> exact sheet and cell range is recorded instead so it can be found again.

## Status board

| # | Item | Area | Status |
|---|---|---|---|
| 1 | Web app is very slow | Performance | ⏸ parked — client reports it is no longer slow; revisit if it returns |
| 2 | Planned % shows 86, Excel says 100 | Data | ✅ **done** |
| 3 | Progress-curve "expected" line — where is it from? | Data | ☑ answered, decision needed |
| 4 | Progress curve doesn't match the Excel curve | Data | ☐ |
| 5 | Financial Progress (BOQ) values look wrong | Data | ☐ |
| 6 | Remove the Gantt chart page | Remove | ✅ **done** |
| 7 | Remove the Milestones page | Remove | ✅ **done** |
| 8 | Discipline table should show Phases, not disciplines | Wrong content | ☐ |
| 9 | Submittals charts unreadable | Wrong content | ✅ **done** |
| 10 | Missing page: 3 pies + planned/actual bar + table | Missing | ☐ |
| 11 | Missing page: Progress Sheet table | Missing | ☐ |
| 12 | Cashflow: 2 charts should be 1, landscape, label the end | Layout | ☐ |
| 13 | Landscape pages use the portrait header/footer | Layout | ✅ **done** |
| 14 | Why are some rows coloured? | Question | ☐ |
| 15 | Zone-progress chart on p13 makes no sense | Wrong content | ✅ **done** (with item 2) |
| 16 | Missing units/currencies in some tables | Polish | ☐ |
| 17 | What does `السابق %` mean? | Question | ☑ answered |
| 18 | Where is `تفاصيل الرسومات والمواد` in the reference? | Question | ✅ **answered + page removed** |

---

## 1. The web app is very slow

**Client:** "first of the webapp is very slow now so please fix that"

**Understood:** The app became noticeably slower recently — this is about the web
UI, not PDF render time. Needs profiling before changing anything. Most likely
candidates: the Customize tab's live-preview fetches (`chart-svgs`, `table-data`,
`toc-entries`, `table-overflow`) now running against a project with 24,377
activities and 7,477 submittals, and the uncached `build_report_context`.

---

## 2. Planned % is 86 in the report, 100 in the Excel

**Client:** "some numbers are wrong for example the charts in the report show that
the planned is 86% when in the excel it shows that it is 100% and the actual is
depending on the zone 99 or 78 or 92 or whatever but the total actual correct
progress of the project from the excel sheet is around 88% so why is the planned
wrong?"

**Understood:** The **actual** figures are right (88% overall, per-zone varying).
The **planned** figure is wrong. Our per-zone planned is computed as elapsed
calendar time between the zone's planned start and finish, capped at 100%
(`services._planned_progress`). The client's Progress Sheet states
`cumulative Plan Performance% = 100.00%` for **every** zone — because the baseline
says all of it should already be finished. So the reference treats planned as 100%
once a scope is past its contractual date, and we show a fraction instead.

**Fixed 2026-09-02.** Planned now comes from the schedule's own baseline figure.

Root cause: the P6 export's `Start`/`Finish` columns are the CURRENT schedule,
which has already absorbed every delay, so measuring elapsed time against them
can never show a project as behind — it read 87.4% on zones whose baseline says
100%. The export also carries **`Schedule % Complete`** (column 15), which is the
baseline's own view and is exactly what the client's Progress Sheet quotes as
`cumulative Plan Performance%`. In this file 24,640 of 24,641 activities carry
1.0, cost-weighted to 100.00%.

The Planex-code importer read nine columns but not that one. Now:
- `Activity.schedule_percent` stores it (migration `0046`);
- `projects.services.scope_planned_map()` rolls it up per scope, cost-weighted,
  mirroring `scope_progress_map`;
- `reports.services._scope_planned_progress()` prefers it, keeping the old
  date-based estimate only for sources carrying no such column (zone trackers,
  older exports);
- the project figure falls back to the weighted mean over activities, because
  the Planex-code tree is built from the code column so the project-title row
  never becomes a root.

Verified: every zone now reads planned **100.0%** against the Excel's 100.00%,
with actual unchanged (96.9 / 99.1 / 80.9 / 95.7 …). 5 new tests.

---

## 3. Where does the progress curve's "expected" line come from?

**Client:** "the progress curve line chart thing we have the expected where did
you get that data from ifrom the excelsheets???"

**Answer:** **Not from the Excel.** It is computed by us — a straight line from the
last actual point to 100% at the project's forecast finish date. The project stores
forecast *dates*, not a month-by-month projected curve, so that was the only
forecast the data supported at the time.

**But the workbook has a real one.** The `progress curve` sheet carries
`Cumm Remaining Cost%` (the red segment in the client's own chart). We should plot
that series instead of interpolating.

---

## 4. The progress curve doesn't match the Excel

**Client:** "why in the image 10 I sent you why do you not make the progress curve
similar to this image cause I feel like the values in the progress curve that we
have is wrong according to the excel sheets please recheck that"

**Reference:** Excel, sheet `progress curve`. Series are
`Cummulative Early Budget Expense %` (row 5), `Cummulative Late Budget %` (row 8),
`Cummulative Actual Cost %` (row 11), `Cumm Remaining Cost%` (row 14); months across
row 2. End labels 83.70% and 100.00%.

**Understood:** Our S-curve should mirror that chart — same series, same shape, and
end-of-line value labels. Ties into item 3: the workbook has all four series and we
currently plot two plus an invented forecast.

---

## 5. Financial Progress according to BOQ looks wrong

**Client:** "the financial progress according to BOQ I feel that something might be
wrong with the one in the report as its values I mean? I feel they might be wrong
so please double check that please and thank you cause the excel sheet shows
something different"

**Our page:** `docs/review-2026-09-02/report-11-boq-financial.png`
**Reference:** Excel — "Financial Progress according to BOQ", budget vs actual per
work category (أعمال الهارد سكيب 59.02% / 26.61%, أعمال الزراعات 5.53% / 0.77%, …).

**Understood:** Compare our chart's numbers to the workbook's category percentages
and find where the derivation diverges.

---

## 6. Remove the Gantt chart page

**Client:** "also please remove this gannt chart from the report (check the image I sent)"

**Our page:** `docs/review-2026-09-02/report-01-gantt.png` — «الجدول الزمني»,
landscape, zone-level bars.

**Fixed 2026-09-02.** Removed from both monthly templates (27 -> 25 pages) and
from the two reports that already carried their own copy in `layout_override`.
The `gantt` chart source stays available in the builder — this removes a page
from one report design, it does not delete a feature.

---

## 7. Remove the Milestones page

**Client:** "another thing is image 4 that I sent I dont see this in any place in
the refrence pdf so please remove that and thank you"

**Our page:** `docs/review-2026-09-02/report-04-milestones.png` — «المعالم الرئيسية»,
a table of milestone / date / status rows.

**Fixed 2026-09-02.** Removed alongside item 6, same treatment; the `milestones`
table source remains available in the builder.

---

## 8. The discipline table should show Phases, not disciplines

**Client:** "also look at the second image shouldnt it show the data of the 3rd
image in the table???"

**Our page:** `docs/review-2026-09-02/report-02-discipline-progress.png` —
«الإنجاز حسب التخصص», columns الخرسانة / المعماري / الكهرباء / الميكانيكا / أخرى,
one row per building.

**Client's scope-tree screenshot:** under Stage → Zone → Area (عمارة A6) the children
are **Phases**: التشطيب الداخلي، السلم، المدخل الرئيسي، الاعمال الكهربائية،
اعمال المصاعد، اعمال مكافحة الحريق، اعمال التيار الخفيف، Snag list.

**Understood:** The table's columns should be the real Phase names from the schedule,
not the five fixed discipline buckets. Today most columns show "—" because the data
doesn't map onto those buckets.

---

## 9. The submittals charts are unreadable

**Client:** "image 7 I cannot understand anything from it so please make the numbers
mean somthing and thank you cause I dont understand what they mean check image 8 to
know what they should look like or explain get what I mean?"

**Our page:** `docs/review-2026-09-02/report-07-submittals-charts.png` —
«موقف الرسومات والمواد».
**Reference:** Excel — two stacked bars, SHOP DRAWING and MATERIAL SUBMITTALS,
categories SUBMITTED / APPROVED / REJECTED / pending, series ARCH / CIVIL / MEC /
ELECTRICAL, the count printed inside every segment, axes to 8000 / 500.

**Fixed 2026-09-02.** Two things were wrong, one of them not the chart's fault.

The shape already matched the reference (statuses down the axis, disciplines
stacked). What it lacked was the reference's leading **SUBMITTED** bar — the
total each discipline has put in, which every other bar is read against. Without
that denominator the counts carry no sense of scale. It is a total, not a status,
so it is derived from the other three rather than imported as a fifth bucket that
would double-count every row. Labels on segments too narrow to hold them are now
suppressed (below 4% of the widest bar): on real data the pending counts printed
on top of each other in a few millimetres.

Verified against the client's own numbers: approved 717 / 2339 / 260 / 326 and
rejected 735 / 1514 / 342 / 667 — exact matches.

The second thing: the Mansoura project itself only carries **10** hand-entered
submittals, so its chart legitimately plots 1s. The counts above come from the
Saint Catherine project, where the dashboard's real matrix was imported. A chart
can only be as readable as its data.

---

## 10. Missing page — 3 pie charts + a planned/actual bar chart + a table

**Client:** "another issue I found is that I cant find this page in the report I
think you did not add it so please do it this show case 4 charts 3 pie charts and
one bar chart the bar chart shows planned vs actual of each Area per stage get what
I mean? and oh I almost forgot that we have in the same page a table too so please
look into that okay?"

**Reference:** Excel `Dashboard`, the "Progress as on: Feb / المنصورة 6 / Phase 1"
block — three pies (PROGRESS: planned vs actual vs variance; DURATION: phase vs
completed vs remaining; Earned Progress: planned value vs earned value vs remaining),
a full-width bar chart «مقارنة بين نسب الانجاز المخططة والفعلية للمرحلة الاولى» with one
planned/actual pair per Area (A6, A7, A8, A15 …), plus the project-info table on the left.

**Understood:** A new page to build — three pies + one wide planned-vs-actual bar
chart per Area within a Stage + the info table, all on one page, per stage.

---

## 11. Missing page — the Progress Sheet table

**Client:** "and image 6 too you did not add this in the reprot so please add this"

**Reference:** Excel "Progress Sheet" — rows grouped by stage
(المرحلة الاولى (75) عمارة …), one row per zone, columns: Unit, Trade, cumulative
Plan Performance%, cumulative Actual % (This Month), This Month Progress %,
cumulative Actual % (Previous Month), Performance Factor %, Variance %.

**Understood:** We *do* have a `progress_sheet` table, but it evidently doesn't match
this. Compare column by column, including the stage grouping in the left column.

---

## 12. Cashflow — one chart, landscape, and label the final value

**Client:** "as you can see from image 9 the cashflow for some reason in the report
we have 2 charts for it when we are supposed to have one and the page needs to be
landscape too not only that but the final number should appear on the line chart as
shown by the image I sent"

**Our page:** `docs/review-2026-09-02/report-09-cashflow-two-charts.png` — portrait,
«التدفق النقدي», two separate charts (monthly bars, cumulative curve).
**Reference:** Excel "Cash flow" — ONE landscape chart combining the monthly bars
with both cumulative lines, end values called out (2,434,402,771 planned /
1,889,559,271 actual).

**Understood:** Three changes to one page — merge the two charts into a single
combined bar+line chart, make the page landscape, and print the final cumulative
value at the end of each line.

---

## 13. Landscape pages use the portrait header/footer

**Client:** "another thing is that when the page is landscape the header and footer
still think they are in portrait mode so please fix this if possible or tell me what
to do or do we need to make some sort of page editor template for pages that are
landscape?"

**Fixed 2026-09-02 — centrally. No separate landscape master is needed.**

`_master_box` already corrected for a page's HEIGHT (that's how footers stopped
falling off landscape pages) but never for its WIDTH, so every header element kept
its portrait x. A right-hand logo authored 25mm in from a 210mm page's right edge
landed two-thirds of the way across a 297mm one, and a centred title sat left of
centre.

Header and footer bands are laid out against page EDGES, so `_master_x` now keeps
whichever edge an element was placed against: left-anchored keeps its left margin,
right-anchored keeps its right margin, centred stays centred, and a full-width rule
keeps both insets and stretches. Classification is by the element's own centre
against the authored page width — no per-element configuration, and portrait pages
are byte-identical (the same-width case returns the authored values untouched).

Verified on a landscape page: MCG at the left edge, title centred, BIM Hive at the
right edge, footer spanning the full width. 6 new tests.

---

## 14. Why are some rows coloured?

**Client:** "and image 13 some reason there is colored rows why is that???"

**Our page:** `docs/review-2026-09-02/report-13-project-info-colored-rows.png` —
«معلومات عن المشروع», with النهاية المتوقعة / التأخير (يوم) shaded.

**Understood:** Explain the rule — I believe it deliberately highlights the
forecast/delay rows (the reference dashboard highlights the same figures) — then
confirm whether the client wants it kept.

---

## 15. The zone-progress chart on page 13 makes no sense

**Client:** "another thing si that this chart does not make sense it is in page 13
I am taking about the image 12 that I sent"

**Our page:** `docs/review-2026-09-02/report-12-zone-progress-chart.png` —
«الإنجاز حسب المنطقة», title reads «الخطط: 100% (تجاوز الموعد التعاقدي الأصلي)»,
x labels PH1 - Z(A), PH1 - Z(D), PH2 - Z(C) …, one red actual bar per zone.

**Fixed 2026-09-02, together with item 2.** Correcting the data was not enough:
both `planned_actual_chart` and `_unit_bars` had an `all_overdue` branch that,
when every zone read 100% planned, dropped the planned series entirely and
replaced it with that note in the title. It was added back when planned was a
meaningless fraction; with planned correct it fired *always*, hiding the very
comparison the chart exists to make — and the client's own dashboard plots the
flat 100% planned bar beside each actual one. The branch is gone, so both series
are drawn whenever a baseline exists.

Only the actual bars carry a printed value (reportlab takes one label format per
series): labelling a flat 100% put "100%" over every bar in one colliding row.
The orphaned `planned_overdue_note` label was removed too.

---

## 16. Missing units / currencies in tables

**Client:** "in some tables you forgot the units for example currencies"

**Understood:** Sweep every money and quantity column and append the unit (EGP, م²,
يوم). Need to enumerate which tables are affected.

---

## 17. What does `السابق %` mean?

**Client:** "another thing is what does this column mean please tell me and thank
you: `السابق %` it is in the progress percentage table per stage table"

**Our page:** `docs/review-2026-09-02/report-xx-progress-percent-previous-col.png`

**Answer:** It means **"Previous %"** — the same scope's cumulative actual progress
as at the *previous* month's snapshot, so the reader can see the movement between
last month and this month. Same idea as the reference Progress Sheet's
`cumulative Actual % (Previous Month)` column (item 11). If the Arabic is unclear we
can relabel it, e.g. «الشهر السابق %».

---

## 18. Where is `تفاصيل الرسومات والمواد` in the reference?

**Client:** "`تفاصيل الرسومات والمواد` this in the report I dont know where it is in
the refrence pdf so please tell me and thank you"

**Our page:** `docs/review-2026-09-02/report-xx-submittals-detail-table.png`

**Answer:** **It isn't in the reference.** It was a page we added — a
row-per-submittal listing behind the two summary charts. The reference only ever
shows the two stacked charts (item 9).

**Removed 2026-09-02**, on the same rule as items 6 and 7 (not in the reference →
not in the report). It was also the page that printed 249 pages of repeated
discipline names on Saint Catherine, whose submittals came from the dashboard as
counts with no per-item titles. The `submittals` table source stays available in
the builder if a real per-item register is ever wanted.

---

## Notes carried over from earlier (still open)

- **Contract value vs invoices** — the Saint Catherine report shows 5,632,996,242 EGP
  contract against 21,913,667,708 invoiced, because the dashboard header and the
  extract-comparison sheet disagree by ~4.4x. The sheet's own revised total is
  24,564,900,940. One field to change if confirmed.
- **The two workbooks describe different projects** — the Dashboard is Saint
  Catherine (41 references, 0 Mansoura), the P6 schedule is Mansoura 6. That project's
  schedule and finances therefore describe different work.
- **Delays page is empty** — no obstacle log exists in either workbook; only delay
  day-counts, already imported as EOT/forecast dates.
- **Orphan table row** — one row of the project-info table lands alone on its own page
  in the Saint Catherine report.
