# Report Builder — Client Feedback & Reference Notes

Organized by phase from the post-meeting feedback (2026-08-11), then revised after
thinking through what's actually safe to build on vs. what needs to be hardened or
rebuilt first. Notes under each phase are only the parts of the two reference files
(`Dashboard template 02-08-2026.xlsx`, `تقرير شهري فبراير 32 - مشروع المنصورة 6.pdf`)
that bear directly on something in the list — nothing extra.

---

## Where the monthly cashflow/invoice updates come from

Both live on the project's **Finances tab**, each with an **"Import Excel"** button
(`.xlsx`/`.xlsm`):
- **Cash Flow panel** — import **replaces the whole table** (full re-read of the
  month-by-month planned/actual row). Monthly workflow: get the updated Dashboard
  Excel → re-upload here → the table refreshes.
- **Invoices panel** — import is an **upsert** (adds new periods, updates existing
  ones) — doesn't wipe history the way cashflow does.

Both expect the same "Dashboard template" Excel shape.

---

## Before the phases: why the order changed from the first pass

Three things found by actually reading the current code (not just the feedback list)
change how this should be sequenced:

1. **The scope/zone rollup code is fragile.** Two real, silent bugs were found and
   fixed in it this session — one made zone data vanish entirely, one rolled progress
   up to the wrong tree level. "Pick a table's data scope, like the Scope tab" means
   generalizing that same code to every table/chart. Hardening it first, rather than
   extending it as-is, avoids planting the same bug in more places.
2. **The canvas preview and the real PDF are two separate implementations** — one is
   the real ReportLab renderer (server-side, produces the actual PDF), the other is a
   simplified mockup (client-side, for live editing). Every new chart type on the list
   would get built *twice* under the current setup, and the mockup still wouldn't
   match. There's already a working pattern for *already-saved* pages: show the real
   rendered PDF page as the background, with invisible click-targets on top. Extending
   that same mechanism to actively-edited pages (re-render the real page a second or
   two after you stop moving something) fixes "preview doesn't match the PDF" directly
   — and means everything built after that point only needs to exist once.
3. **Tables are bound to fixed backend data sources today** — there's no free-form
   table. "Paste from Excel, build a custom table" isn't an extension of that system,
   it's a new one next to it, so its data model needs deciding up front, not discovered
   mid-build.

Net effect: **preview parity moved up** (was last, now second) so nothing gets built
twice, and the scope-picker work waits until the underlying code is solid.

---

## Phase 1 — Bug fixes

- Resize/rotate glitches (no repro steps yet)
- Right sidebar's horizontal scroll bug
- Right sidebar missing "change/upload image" control when an image element is selected
- Undo/redo buttons in the toolbar (logic already exists via Ctrl+Z — just needs buttons)

---

## Phase 2 — Preview parity *(moved up — see reasoning above)*

- Make the actively-edited canvas show the real rendered page, not the simplified
  mockup — extends the existing "real background image + invisible hit-boxes" pattern
  (already used for saved pages) to cover live edits too.

Everything in Phases 4 and 5 below builds on top of this — chart/table types added
after this point only need to be implemented once.

**Found while testing Phase 1** (2026-08-12): the endpoint that rasterizes real page
backgrounds for the Customize tab (`page-images`) can fail outright on a large report
— `Failed to proxy ... [Error: socket hang up] { code: 'ECONNRESET' }`. This is the
same class of problem already solved for the main PDF download: Next's `/api` rewrite
proxy resets long-running upstream responses (~60s), and the PDF route was moved to
its own dedicated route handler (`app/reports/[id]/pdf-file/route.ts`) to work around
it. `page-images` does the same heavy rendering internally but was never given the
same treatment, so it can 500 on exactly the reports big enough to need this feature.
Worth fixing as part of this phase, since Phase 2 depends on this exact endpoint
working reliably.

---

## Phase 3 — Editor interaction, Canva-parity

- Multi-select → move/resize several elements together
- Bottom page strip: scroll through pages, duplicate/reorder, thumbnails (like Canva)
  — cheaper than it looked once Phase 2 exists, since it can reuse the same real-page
  rendering instead of needing separate thumbnail generation
- Better image controls: real crop tool, better resize handles
- Shift+scroll to zoom, scroll to pan across pages

---

## Phase 4 — New authoring capabilities

- Blank "title-only" divider page pulled from the TOC entry name — this pattern
  already exists in the legacy renderer (`dividers` config), just needs porting into
  the canvas as a real element type
- **Scope-resolution code hardened first**, then: bind a table's data to a specific
  zone/stage, same pattern as the report's Scope tab
- Paste a table from Excel + build/edit a fully custom table (add/remove rows,
  columns, cells) — biggest, most novel item in this phase; needs its data model
  decided before any UI is built on top of it
- Project Description needs to support **embedding tables/images/charts inline**
  within the text, not just formatted paragraphs — a different problem from the
  custom-table work above, since this is content mixed into flowing text rather than
  a standalone box on the page
- Logos: confirm the real cap — may already support more than 3 via the data model
- Per-page landscape override (today orientation is one setting for the whole template)
- Upload a PDF → pick which pages to pull in as images/attachments
- 4 TOCs (Contents / Tables / Charts / Images), each a clickable link to the right page

Confirmed real in the reference PDF: 3 of the 4 TOCs (Contents, Tables, Figures) exist
already in their live workflow, dot-leader style, matching what Planex's TOC element
already does. Every table and chart also carries a sequential number ("جدول 1", "رسم
توضيحي 1"...) with a caption printed under it, not just listed in the TOC — the
legacy Planex renderer already does this for charts, needs porting to the canvas.

---

## Phase 5 — Chart/table standards + visual match to the reference

- Every chart/table needs a real title + axis/unit labels
- Charts should visually match the reference Excel exactly — each new type below only
  gets built once, thanks to Phase 2

Pulled the real chart objects out of the Dashboard workbook directly (not just the
screenshot). A few chart types genuinely have no equivalent in Planex yet: Material
Submittals and Shop Drawing (stacked bars by discipline), a 4-line Progress Curve
(Planex's S-curve is 2-line), and Financial Progress by BOQ. Also: the reference's
Progress Curve sheet is cost-based (cumulative expense), not %-complete — needs
confirming which one to match before building it.

Project Info table also carries dual-currency values (EGP + USD) and a split between
original BOQ value and added-items value in the reference — smaller gap, but real if
Project Info should match exactly too.

---

## Phase 6 — Final template build

Cover → 4 TOCs → Summary (landscape, dashboard-style) → Project Info → Description
(rich text, can embed tables/images/charts inline) → Progress Report → الموقف
التنفيذي → Project Durations (status charts) → Cash Flow (bar + line) → Invoices
(waiting on more info) → Areas of Concern → Attachments.

**Progress Report** needs three distinct things, not two: the S-curve, a separate
planned/actual/variance **percentage breakdown chart** (the donut split shown in the
reference), and the 3 progress-tracking charts from the reference image. All three
are chart types Phase 5 needs to cover, not one merged item.

**الموقف التنفيذي** is the flagship use case for the Phase 4 scope-picker — the
tables here need planned progress, actual, *and delay days* as columns, scoped to
whichever level you pick (zone / area / stage), plus an actual-vs-planned chart for
that same chosen scope. This is exactly what "bind a table's data to a specific
zone/stage" in Phase 4 is for — without that feature, this page can't be built the
way it's described. Progress images also live on this page.

The Summary page in the reference is dense — around 12 distinct panels on one
landscape page (project info, progress bars, duration pie, invoice-status pies, a
cashflow combo chart, the progress curve, per-zone bars, submittals/shop-drawing bars,
BOQ financial progress, SPI gauge, photo strip, areas-of-concern text). Worth treating
as its own piece of work inside this phase, not "just the dashboard page."

The per-zone/stage executive-dashboard pages (الموقف التنفيذي) in the reference match
Planex's existing per-zone Area Dashboard repeat-page pattern well — lower risk than
the Summary page.
