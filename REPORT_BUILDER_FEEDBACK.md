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
working reliably. **Resolved as of commit 2c926a2** — the whole page-snapshot
mechanism (`page-images` included) was retired rather than patched, so this
specific failure mode no longer exists.

**Found while testing Phase 2** (2026-08-18): with the live Customize-tab preview
and the real PDF now rendering from the same data (the point of this phase), a
side-by-side check of both against the actual PDF surfaced real *content* bugs —
not preview/rendering mismatches, genuine problems in the report's own data/logic:

- **Critical Path Delays table (`critical_path` / "المسار الحرج للتأخيرات") shows
  0 days delay on every single row, for every zone** — contradicts the same
  report's own executive dashboard, which reports 426 days of project delay, and
  zones visibly behind on progress (some at 54–61% actual vs. 100% planned).
  Root cause: `services._critical_path_rows` only computes delay as
  `today − zone.planned_finish`, so a zone can't show slippage until its own
  deadline has already passed — every zone's `planned_finish` in this project is
  still months out (Aug–Oct 2026), so the math is technically consistent but the
  table can never do what its own docstring says it's for ("which buildings are
  slipping and by how much"). This is exactly the delay-days column Phase 6's
  الموقف التنفيذي section calls for — worth fixing before that page gets built on
  top of it. Also worth confirming: those per-zone `planned_finish` dates are
  *later* than both the project's contractual finish (26 Apr 2025) and its revised
  finish (26 Jun 2026) — backwards for a baseline date, possibly a P6-import issue
  (see the `FOR (P6)` sheet TODO above).
- **The same short zone code (e.g. "Z(A)", "Z(C)") repeats 2–4 times** across the
  executive dashboard's bar chart and the Critical Path Delays table, for
  genuinely different zones (confirmed distinct IDs, dates, and progress) — no way
  for a reader to tell them apart. Relevant to the Phase 4 scope-picker and Phase
  5's "every chart/table needs a real title" — these zones need a real
  disambiguating label surfaced into compact chart/table views, not just their
  short code.
- **S-curve's "actual" line has a small rendering kink** — a visible dip-and-recover
  partway through what should be a flat plateau segment, on the executive
  dashboard. Cosmetic, but real.
- **Per-zone duration widget doesn't reconcile with the project-level one** — a
  zone's own donut (e.g. its Area Board page) shows "1846 days duration, 0 delay"
  against the executive dashboard's "1200 days, 426 delay" for the same project —
  same root cause as the Critical Path Delays bug above (`_zone_duration` uses the
  zone's own dates when present, and those dates disagree with the project's).
- ~~**Zone building-breakdown tables silently truncate to 6 rows**, with a "+27 more
  rows" caption that's a dead end in a static downloaded PDF — fine in an
  interactive viewer, not in a PDF a client actually reads.~~ **Fixed** — a table
  with more rows than fit its box now genuinely continues onto extra pages
  (`pdf_canvas.py`'s `_expand_table_overflow`/`_split_table_chunks`, backed by
  `Table.split()` called repeatedly the same way a Platypus Frame pages a
  flowable, since this renderer draws each page at fixed positions rather than
  flowing a story through frames) — verified on the real report: 25 → 53 pages,
  zero "more rows" notes left, every row's real data present, running header
  still repeats on every continuation page. The live Customize-tab canvas
  doesn't synthesize matching extra pages into the editor's own page list (a
  much bigger UI change) — it now **scrolls** the table within its box
  (`overflow-y: auto`, not a hard clip) so every row stays reachable/editable
  there too, plus a "continues in the downloaded PDF" note when it's taller
  than the box.

---

## Phase 3 — Editor interaction, Canva-parity

- **Multi-select → move/resize several elements together** — built. Found and
  fixed two real bugs during testing: (1) the group-selection bounding box was
  intercepting clicks meant for individual members, so Shift-click-to-deselect
  one element out of a multi-selection silently did nothing (fixed by making
  the box `pointer-events: none`, keeping only its resize handles clickable);
  (2) drag-to-select (marquee) also triggered the browser's native text
  selection over whatever it crossed, painting its own highlight over the
  marquee rectangle (fixed with `preventDefault()` + `user-select: none`).
- **Table styling (Canva-style)** — built: a table element's header fill/text,
  cell text color, bold header, font size, row height (cell padding), zebra
  stripe + color, and border + color are now real, per-element controls in the
  Properties panel — the `zebra`/`border`/`header_bg`/`header_text` fields
  already existed there but were dead (the real PDF never read them, only
  `source` — see `_draw_table_element`'s old docstring); wired end-to-end now
  through `pdf_tables.table_style_override`, the same helper both the real PDF
  table builders and the live Customize-tab preview use, so a styled table
  can't show a look the download doesn't also produce. Verified against a real
  rendered PDF (magenta header, gold zebra stripe, blue border, 16pt text, all
  came through correctly). Column width / per-cell formatting deliberately
  **not** attempted — a real per-cell spreadsheet model is a much bigger
  change none of the three table kinds are built to express; this stays at
  the same one-style-per-table granularity the real PDF builders already have.
- **Bottom page strip [built]** — a horizontal thumbnail row under the canvas
  (`PageStrip.tsx`), click to jump pages, plus duplicate/delete/add right
  there. Turned out *not* cheap to reuse real-page rendering for, the way the
  original note above assumed — that mechanism (a rasterized snapshot per
  page) is exactly what got retired in Phase 2, and rendering 25-50+ *live*
  pages (real chart SVGs, real table data) simultaneously just for small
  thumbnails would be genuinely slow. Built as lightweight wireframes instead
  — each element as a flat-colored box sized/positioned from its real x/y/w/h,
  colored by type, no live data fetched — so it stays instant regardless of
  page count. The existing left-side page list (rename, move up/down, repeat
  toggle) is untouched and still there; this is a second, faster way to
  visually scan and jump, not a replacement.
- **Image crop tool [built]** — an "image" element's Fit=Cover option existed
  in the Properties panel but, like the table styling props, was dead — every
  draw call (frontend CSS *and* the real PDF's `_draw_image`/
  `_draw_uploaded_image`) only ever did "contain" (letterboxed, never
  cropped), regardless of `fit`. Built real cover-crop for both sides
  (`pdf_layout.draw_fitted_image`, clipped `drawImage` scaled to fill; CSS
  `object-fit`/`object-position` on the frontend — identical math), plus two
  new `focal_x`/`focal_y` (0-100%) properties so you can choose *which* part
  of an oversized image survives the crop — same convention as CSS
  object-position. The crop-positioning math is unit tested directly
  (`CoverFitGeometryTests`, 7 cases covering both axes and the PDF-vs-CSS
  y-direction flip) rather than only checked by eye. "Better resize handles"
  from this same bullet not otherwise addressed — the existing 8-handle
  resize (shared with every element type) already got the rotation-aware
  rewrite a few commits back and no specific complaint about it exists to
  work from; flag a concrete one if there's a real issue with it.
- **Shift+scroll to zoom, scroll to pan [built]** — zoom is now continuous
  (any value between 25%-300%, not just the five preset steps) via
  Shift+scroll on the canvas; a plain scroll still pans natively
  (`.canvasScroll`'s own `overflow: auto` always did that, nothing to add).
  The +/- buttons still step through the same preset list, now finding the
  nearest preset *above/below* the current continuous zoom rather than
  looking for an exact match (which shift-scrolling to an in-between value
  would never hit). Verified with real dispatched wheel events: Shift+scroll
  changed 100%→120% by the exact expected amount; a same-sized plain scroll
  changed nothing.

---

## Phase 4 — New authoring capabilities

- ~~Blank "title-only" divider page pulled from the TOC entry name — this pattern
  already exists in the legacy renderer (`dividers` config), just needs porting into
  the canvas as a real element type~~ **[built]** — turned out not to need a
  dedicated page type at all: a new `page.title` field source (alongside the
  existing `page.number`) resolves to this exact page's own name (the same
  string `inst.page.get("name")` the TOC already lists it under), so dropping
  one `field` element with that source on an otherwise-blank page reproduces
  the legacy `dividers` look — centered, large, bold. Added a ready-made
  "Divider heading" item to the palette (Setup category) pre-styled that way,
  plus an end-to-end test confirming the title shows on its own page and
  nowhere else across a multi-page render.
- ~~**Scope-resolution code hardened first**, then: bind a table's data to a specific
  zone/stage, same pattern as the report's Scope tab~~ **[built]** — a new
  `scope_zone_id` prop on table/chart elements filters the already-computed,
  already-hardened `ctx["zones"]`/`ctx["hierarchy"]` down to one matching
  zone before either builds its rows/drawing (`resolve_table`/`resolve_chart`
  in pdf_canvas.py) — no new DB queries, no second scope-computation path to
  keep in sync with the report-level Scope tab's own `_scope_context`. A
  "Scope to one zone" dropdown in the Properties panel (table *and* chart
  elements, Customize tab only) lists the report's real zones by name.
  Verified live: picking "Z(A)" narrowed a planned/actual bar chart from all
  15 zones down to exactly one bar group, immediately, in the real preview
  — plus 5 backend tests covering both table sources and both chart
  outcomes (matched vs. non-matching id). This is exactly what الموقف
  التنفيذي (Phase 6) needs a table/chart pair scoped to one zone for.
- Paste a table from Excel + build/edit a fully custom table (add/remove rows,
  columns, cells) — biggest, most novel item in this phase; needs its data model
  decided before any UI is built on top of it
- Project Description needs to support **embedding tables/images/charts inline**
  within the text, not just formatted paragraphs — a different problem from the
  custom-table work above, since this is content mixed into flowing text rather than
  a standalone box on the page
- ~~Logos: confirm the real cap — may already support more than 3 via the data
  model~~ **Confirmed** — no cap anywhere in the stack. `services.py`'s
  `proj_many()` returns every logo-type `ProjectImage` unsliced, and a logo
  element's `slot` is a free number field, not restricted to 0-2; the
  palette's "Additional logo" hint already says "any number," and that was
  already true. Nothing to build.
- ~~Per-page landscape override (today orientation is one setting for the whole
  template)~~ **[built]** — a page's own `orientation` now overrides the
  template default (`pdf_canvas._page_size_mm` takes the page, not just the
  design; ReportLab supports a genuinely variable page size across one
  Canvas via `setPageSize` before each page — the same mechanism the legacy
  renderer's one hardcoded-landscape dashboard page already relied on, just
  made into a per-page *choice* instead of a fixed special case). A new
  toggle button in the Pages panel (landscape-page icon) flips a page
  between "inherit the template default" and "pinned to the opposite
  orientation." Verified live: toggling swapped the canvas's rendered page
  from 462×653px to 653×462px exactly, and its page-strip thumbnail
  followed — plus an end-to-end PDF test confirming the two pages come out
  as genuinely different physical shapes (portrait taller, landscape wider,
  same paper swapped) not just a config flag nothing reads.
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

**Arabic legend text sometimes rendering backwards [fixed]**: found two real
instances of the same root-cause gotcha as the description rich-text bug —
`shape()` (reshape + bidi) called on *part* of a string with plain text
concatenated on afterward, instead of shaping the whole composed string as
one logical unit. The SPI gauge's "SPI= 88%" value line (`f"{shape(title)}=
{v:.0f}%"`) and the Gantt chart's "— Revised finish" slip note (`"— " +
shape(...)`) both had this; fixed by moving the `shape()` call to wrap the
whole string. Every `_legend()` call site itself was already correct (it
shapes its caller's whole label string, not a fragment).

**Chart "cropped from the top" — investigated, not reproduced**: pulled all 9
real chart SVGs the live report currently serves and measured actual
rendered bounding boxes in a real browser (`getBBox()`, not just reading
coordinates) against each one's viewBox — none show content above the top
edge, at the box's real size or synthetically shrunk down to 15mm tall.
Whatever's being seen needs a screenshot or the exact report/chart/tab to
pin down further; didn't want to guess-fix without evidence.

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
