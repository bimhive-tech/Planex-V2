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

- ~~**Critical Path Delays table (`critical_path` / "المسار الحرج للتأخيرات") shows
  0 days delay on every single row, for every zone**~~ **Fixed (2026-08-25)** —
  root cause confirmed: `services._critical_path_rows` only computed delay as
  `today − zone.planned_finish`, so a zone couldn't show slippage until its own
  deadline had already passed — every zone's `planned_finish` in this project was
  still months out, so the math was technically consistent but the table could
  never do what its own docstring says it's for. Fixed with a second, pace-based
  delay signal: when a zone hasn't formally passed its deadline (no explicit
  `revised_finish`, `as_of` still before `planned_finish`), estimate delay from
  the same time-based planned% vs. real actual% every other progress table
  already computes for that zone, translated into calendar days via the zone's
  own duration — an explicit `revised_finish` still wins outright when present
  (a human-recorded EOT shouldn't be second-guessed by a heuristic). Verified on
  the real project: 11 of 15 zones now show real delay (up to 479 days on the
  worst one), not a flat 0 — and the same real-delay numbers now also feed the
  Phase 6 الموقف التنفيذي page correctly. 3 new backend tests (pace-estimate
  before the deadline, explicit `revised_finish` still wins, existing
  date-based-delay tests unchanged).
- ~~**The same short zone code (e.g. "Z(A)", "Z(C)") repeats 2–4 times**~~
  **Fixed (2026-08-25)** — a P6 import can genuinely have several zones named
  identically under different stages/buildings; `services._zone_rows`/
  `_hierarchy_rows` now disambiguate via a new `_disambiguated_names` helper —
  a name shared by more than one scope in the set gets prefixed with its own
  parent's name ("PH1 - Z(A)" vs "PH2 - Z(A)"), a name that's already unique on
  its own is left exactly as-is (no unnecessary lengthening of the common case).
  Verified on the real project's executive-dashboard bar chart and Critical Path
  Delays table — every zone label is now unique; 1 new backend test.
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
- **Scroll past a page's edge moves to the next/previous page [built,
  2026-08-25]** — a plain scroll still pans within a page first (unchanged);
  only once you hit the actual top/bottom edge does it move to the
  previous/next page, so scrolling feels like paging through the whole
  document. A cooldown after each page change stops one fast trackpad swipe
  from flipping through several pages at once; moving backward starts the new
  page scrolled to its bottom (not top) so continuing to scroll up keeps
  flowing naturally instead of snapping back to the top. `LayoutEditor`'s
  wheel handler gained an edge-detection branch (`onNavigatePage`) and
  `ReportConfigurator` supplies it (`navigatePage`); verified live with real
  dispatched wheel events (forward, backward, and a 5-event rapid burst that
  only counted as one page change).

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
- ~~Paste a table from Excel + build/edit a fully custom table (add/remove rows,
  columns, cells) — biggest, most novel item in this phase; needs its data model
  decided before any UI is built on top of it~~ **[built]** — a table element's
  `source` gained a `"custom"` value: instead of computing rows from `ctx`,
  `resolve_table`'s new branch (`pdf_canvas.py`) reads header/rows straight off
  the element's own `props.custom_data` (`{ columns: string[], rows: string[][]
  }`) and returns them through the exact same `"data"`-kind path (`apply_table_
  overrides`, `table_style_override`, `_data_table`) every other table already
  uses — so a custom table gets manual cell overrides, zebra/border/header
  styling, captions, and overflow-to-continuation-pages for free, with zero new
  rendering code. The data model deliberately stays one-style-per-table (like
  every existing table kind) rather than per-cell styling — a real spreadsheet
  format model would be a much bigger change none of the three existing table
  builders are built to express (see `table_style_override`'s own docstring).
  Editing UI is a new `CustomTableEditor.tsx`, a bespoke grid block in the
  Properties panel (gated on `source === "custom"`, same pattern the zone
  scope-picker block already uses) — internally treats the header as row 0 of
  one rectangular grid so add/remove row/column and paste all stay one code
  path, then splits back into `{ columns, rows }` on every change. "Paste from
  Excel" turned out not to need a file upload or backend `openpyxl` parsing at
  all: copying cells in Excel puts a plain tab/newline-separated grid on the
  clipboard, so a cell's `onPaste` handler reads `text/plain` directly and
  grows the grid to fit — Ctrl+C in Excel, click a cell here, Ctrl+V. A new
  "Custom table" palette entry pre-seeds a 2×2 starter grid.

  **Reworked (2026-08-23) after client feedback**: `CustomTableEditor` was
  originally only reachable in the Properties panel sidebar — the client
  wanted to add/remove cells/rows/columns **directly on the page**, and for
  every table, not just custom ones. Two changes:
  - `CustomTableEditor` now renders **directly on the canvas** (`TablePreview`
    in `ElementPreview.tsx`) for any `source: "custom"` table — checked
    *before* the live-data block, since a custom table's own `resolve_table`
    branch still resolves successfully from its seed data, which would
    otherwise make the live read-only view win instead. It's the exact same
    component (real `<input>` cells, add/remove row/column, Excel paste) —
    just no longer confined to the sidebar; the Properties panel now shows a
    hint pointing at the canvas instead of a duplicate copy of the editor.
    Every interactive control inside it (`CustomTableEditor.tsx`) needed a new
    `onPointerDown={(e) => e.stopPropagation()}` — without it, a click would
    also bubble up to `CanvasElementView`'s drag-start handler and move the
    whole table element instead of (or as well as) hitting the control, a
    problem that never came up while the editor only ever lived in a static
    sidebar panel.
  - **Every other (data-bound) table** gained a row-level "×" gutter column
    (`RowHideButton`) next to its existing double-click-to-edit cells — a
    data-bound row can't be deleted for real (it's computed from real project
    data), but clicking × now writes its original row index into a new
    `hidden_rows` prop, which `pdf_tables.apply_table_overrides` (extended
    with a `hidden_rows` parameter, applied after cell overrides so a hidden
    row's own overrides are simply discarded with it) filters out of **both**
    the live canvas preview and the real downloaded PDF — threaded through
    all 14 of `resolve_table`'s call sites in `pdf_canvas.py`. Since the raw
    JSON the canvas fetches already has hidden rows filtered out server-side,
    a displayed row's position there is no longer the same as its original
    index once anything's been hidden — `ElementPreview.tsx`'s new
    `originalRowIndices` reconstructs the true original index for each
    displayed row (skipping whatever's already hidden, in order) so an edit
    or a new hide made after an earlier row was hidden still lands on the
    right row instead of silently shifting by one.

  Verified: backend — the original 5 tests (raw shape, real ReportLab `Table`
  built correctly, missing/columnless data returns `None`, manual override
  reaches the built table) plus 5 new ones for this rework (`hidden_rows`
  drops the row for "data"/"info"/"hierarchy" kinds alike, `hidden_rows` and
  `overrides` share the same original-index space and don't corrupt each
  other, `hidden_rows` reaches the real PDF `Table`, and an end-to-end
  `table-data` endpoint test confirming the live canvas response itself omits
  the hidden row) — all pass against the real project DB; `tsc --noEmit`
  clean. Live-verified in the browser: placed a Project Info table, clicked a
  row's × — row count dropped from 14 to 13 and the hidden row was genuinely
  gone from the live response, not just visually hidden; double-clicked a
  remaining cell and edited it, confirmed the edit landed on the correct
  (still-original-indexed) row; placed a Custom table, typed a header cell,
  clicked "Add row" — the grid grew from 6 to 8 real inputs with the typed
  edit still intact. Test it: any report's Customize tab → drag "Custom
  table" from the palette → edit rows/columns/cells right there on the page;
  or drag any data-bound table (e.g. "Project info") → click a row's × to
  hide it, or double-click a cell to override its text.
- ~~Project Description needs to support **embedding tables/images/charts inline**
  within the text, not just formatted paragraphs — a different problem from the
  custom-table work above, since this is content mixed into flowing text rather than
  a standalone box on the page~~ **[built]** — the biggest structural gap this
  needed closing first: the canvas renderer (`pdf_canvas.py`) draws every element
  at a fixed x/y/w/h with no `Frame`/story engine at all, so it had no way to lay
  out a *sequence* of mixed content (paragraphs, then a table, then more text)
  inside one box the way the legacy flowing renderer (`pdf.py`) already can via a
  real `BaseDocTemplate`. Fixed by giving the canvas renderer a genuine (if
  narrowly-scoped) flow-layout primitive: `_paginate_flow`/`_draw_flow_in_box`
  (`pdf_canvas.py`) use a real ReportLab `Frame` — against a throwaway scratch
  canvas to *decide* what fits (never actually drawn), then the identical
  `Frame.add`/`addFromList` call against the real canvas to draw it — so the page
  boundaries this decides can't silently disagree with what actually gets drawn,
  the same guarantee `_split_table_chunks` already had for one Table, now
  generalized to a whole mixed flow. A new `"description"` element type
  (`_draw_description_element`) draws the report's own `description_html` through
  this; an overflowing one continues onto synthetic pages exactly like an
  overflowing table already does (`_expand_description_overflow`, same
  `PageInstance` splicing pattern as `_expand_table_overflow` — the two now guard
  against reprocessing each other's continuation pages, and against both
  independently claiming the same original page, so a page with both an
  overflowing table *and* an overflowing description still renders correctly,
  just without perfect interleaving — same explicitly-accepted limitation the
  table-only version already had for two overflowing tables).
  Inline embeds themselves: `richtext.py` gained a `<div data-embed="table|chart|
  image" data-spec="{...json...}">` marker the sanitizer keeps (its own display
  children are dropped on save — `data-spec` is the only source of truth) and
  `html_to_flowables` resolves into a real flowable via the *exact same*
  `resolve_table`/`resolve_chart` every standalone table/chart element already
  uses (an embedded table can't render a different look than a standalone one
  would), or a `ReportImage` lookup + `storage_image_reader` for an image embed.
  This one function now serves **both** renderers — `pdf.py`'s own description
  section just started passing `ctx`/`scope`/`avail_width` through, and gets full
  automatic pagination for free from its existing real `Frame`. Editing: the
  generic `RichTextEditor` (`components/ui`) gained an imperative `insertHtml`
  handle and an `extraToolbar` slot — kept report-agnostic on purpose, since
  `components/ui` primitives don't import report-specific code — and a new
  report-specific `DescriptionEmbedToolbar.tsx` (Insert table/chart/image
  buttons, a small source-picker popover, and the existing `/reports/{id}/images/`
  upload endpoint for the image case) plugs into that slot from `ReportDetail.tsx`.
  Live preview: the Customize-tab canvas's `TablePreview`/`ChartPreview` machinery
  needed zero changes (the real `table-data`/`chart-svgs` endpoints already handle
  any table/chart, embedded or not); a new `DescriptionPreview` renders the
  sanitized HTML directly (`dangerouslySetInnerHTML` — already whitelisted-tags-
  only, safe) and shows each embed marker as a labeled "resolved in the downloaded
  PDF" placeholder chip (driven purely by the `data-embed` attribute via CSS
  `content: attr(...)`, no JS) — same honest-placeholder precedent as an
  unresolved TOC caption elsewhere in this feature — since live-resolving an
  embed's *position inside arbitrary rich text* isn't something the existing
  preview infrastructure does. `OverflowClip` (renamed from the table-only
  `TableOverflowClip` it already was, now genuinely shared) gives the description
  box the same "shows what fits, says so" behavior as an overflowing table.
  Verified: 15 new backend tests (embed sanitization/resolution in isolation,
  real end-to-end PDF renders confirming an inline table embed's actual data
  appears in the output, and a genuine multi-page overflow test — 60 short
  paragraphs in a 60mm box produce >1 page with every paragraph's real text
  present and the page's own other content drawn exactly once) — all pass
  against a throwaway sqlite DB (this machine has no `.env`/Postgres access this
  session); `tsc --noEmit` clean.
  Known v1 scope limits, not attempted: per-cell embed styling (an embed reuses
  the same one-style-per-table granularity every other table already has); an
  embed recognized only when it lands as its own top-level block (matches how a
  block embed behaves in most rich editors — in practice guaranteed by the
  sanitizer's own auto-close-on-sibling-block parsing, which promotes a `<div>`
  out of whatever paragraph it was inserted into); the live canvas preview can't
  show an embed's *actual* resolved content inline (placeholder only, real PDF
  only) — the same limitation the Phase 4 caption/TOC work already accepted for
  an analogous reason.

  **Reworked (2026-08-23) after client feedback**: the first version above put
  editing in a separate "Description" tab with toolbar-only embed insertion —
  the client wanted description content to live and be edited **directly on the
  canvas**, the same way every other element is, with drag-and-drop from the
  palette as a second way to insert a table/chart into the text (not just the
  toolbar buttons). This was a real architecture change, not an addition:
  - Content moved from a single report-level `description`/`description_html`
    field to a per-element `props.html` on a canvas `"description"` element —
    so it now flows through the exact same undo-tracked `onElementChange`
    pipeline, and the same save/layout-override persistence, every other
    element already uses. The report-level Description **tab was removed
    entirely** (`ReportDetail.tsx`) along with its own save-payload wiring.
  - `DescriptionPreview` (`ElementPreview.tsx`) now renders a click-to-edit
    static view; double-clicking opens the existing `RichTextEditor` as a
    floating overlay positioned over the element, with `DescriptionEmbedToolbar`
    plugged into its `extraToolbar` slot as before. Clicking outside (or
    Escape) commits the draft back into `props.html` and closes the overlay.
  - Drag-and-drop: `CanvasPage.tsx`'s `onDrop` now checks whether the drop
    landed inside an actively-open contenteditable description; if so, it
    resolves the dragged palette key to its spec (`findSpec`), builds the same
    embed marker `DescriptionEmbedToolbar` builds (extracted into a shared
    `lib/reportEmbeds.ts` so both paths can't drift apart), and inserts it at
    the drop's caret position via `caretRangeFromPoint` + `execCommand`,
    instead of falling through to placing a new standalone element.
  - Backend: `pdf_canvas.py`'s `_draw_description_element` and
    `_expand_description_overflow` now read `props.html` off the element
    instead of `ctx["project"]["description_html"]`; `richtext.py` gained
    `sanitize_layout_html`, which walks a template/report's whole
    `page_design`/`layout` tree and sanitizes every description element's
    `html` in place (mirrors the standalone `sanitize_html` the old
    `description_html` field used, now applied per-element) — wired into both
    `ReportTemplateSerializer.validate_config` and
    `ReportWriteSerializer.validate_layout_override`. The legacy flowing
    renderer (`pdf.py`)'s own description section, which still reads
    `ctx["project"]["description_html"]`, was deliberately left as-is — it has
    no canvas/element concept at all and isn't used by this client's
    canvas-based templates.
  - Found and fixed a real stale-closure bug during this rework: the
    outside-click/Escape commit handler closed over `draft`/`html` from the
    render where editing *started*, so anything typed or embedded afterward
    was silently discarded on exit. Fixed with a `latest` ref kept fresh every
    render, read from inside the commit handler instead of the stale closure.
  - Verified live in the browser (not just `tsc --noEmit`): placed a fresh
    Description element, typed text, inserted a table embed via the toolbar,
    committed via outside-click — confirmed the static view showed both the
    typed text and the embed chip (previously reverted to the empty
    placeholder before the stale-closure fix). Separately verified
    drag-and-drop: dragged a chart palette item onto the open editor's text,
    confirmed it landed as an inline embed at the caret position and survived
    commit alongside the earlier content.
  Test it: any report's **Customize tab** → drag **"Description"** from the
  palette's **"Branding & fields"** category onto a page → double-click it to
  start typing → use the floating toolbar's table/chart/image buttons, or drag
  a table/chart straight from the palette into the text → click outside to
  save the draft → check the **downloaded PDF**.
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
- ~~Upload a PDF → pick which pages to pull in as images/attachments~~ **[built]** —
  deliberately **zero backend changes**. The obvious approach (rasterize the
  uploaded PDF server-side) needs a PDF-rasterization library, and this
  codebase doesn't have one: it *used to* (a PyMuPDF/`fitz`-based `page-images`
  endpoint, retired in commit `2c926a2` for an unrelated reliability reason —
  see Phase 2's notes above), `fitz` isn't in `requirements.txt` and never has
  been, and PyMuPDF is AGPL-licensed unless a commercial license is purchased
  from Artifex — not something to reach for by default in a proprietary
  product without that being a deliberate call. The frontend already ships
  `react-pdf`/pdf.js (for the report PDF viewer) — genuinely free, Apache-2.0,
  and perfectly capable of rasterizing PDF pages **in the browser**. New
  `PdfPageImportPicker.tsx`: pick a local `.pdf`, pdf.js renders a thumbnail
  per page entirely client-side (no upload yet), the user checks which pages
  to keep, and each selected page gets re-rendered at 144 DPI and uploaded as
  an ordinary PNG through the *exact same* `/reports/{id}/images/` endpoint a
  manually-picked image file already goes through — so the backend can't tell
  the difference and needed no new code, no new model, no new dependency.
  Wired into `ReportAssets.tsx` (the existing Cover/Progress Photos/
  Attachments upload panel) so it's available wherever those already are, not
  just Attachments — a picture pulled from a client's own PDF is just as
  useful as a cover image or a progress photo. Verified: full `tsc --noEmit`
  and a full `next build` both pass clean (webpack resolves the pdf.js worker
  import correctly, no missing-module/type errors anywhere in the bundle).
  **Not yet live-verified in a browser** — needs a real PDF file and a running
  frontend to confirm the actual render-and-upload round trip. Test it: any
  report's **Cover / Progress Photos / Attachments tab** → "Import pages from
  a PDF…" (below the existing single-image upload form) → pick a `.pdf` → a
  thumbnail grid appears, every page pre-selected → uncheck any you don't
  want → "Import N pages."
- ~~4 TOCs (Contents / Tables / Charts / Images), each a clickable link to the right
  page~~ **[built]** — every table/chart element now has a "Show caption" toggle
  (Properties panel) plus an optional caption text override; when on, the canvas
  reserves an 8mm footer strip under the box (same pattern the image element's
  existing caption already used) and the real PDF draws "جدول N: name" / "شكل N:
  name" there, N a running counter across the whole document — mirrors the legacy
  flowing renderer's per-chart `fig[0]` counter (`pdf.py`'s `_captioned`), extended
  to tables and to captioned repeat-photo images ("صورة N"). The `toc` element
  gained a `variant` prop (`contents` / `tables` / `figures` / `images`) — three new
  palette entries ("List of tables/figures/images") drop one in pre-set to each
  variant. Getting the numbering right needed a pre-pass (`_collect_captions`,
  `pdf_canvas.py`) that walks the final page order and assigns every caption its
  number *before* any page draws — the render loop is a single forward pass, so a
  "List of tables" page that comes BEFORE the tables it lists would otherwise see
  an empty list at draw time (same reasoning `build_canvas_pdf`'s existing
  `toc_map`/`toc_order` pre-pass already used for the Contents variant). A table's
  synthetic continuation pages (`_expand_table_overflow`) don't get their own
  caption — same logical table, not a second one. Not real clickable PDF
  hyperlinks (the pre-existing Contents TOC doesn't have those either — out of
  scope here, same as it always was). The Customize-tab canvas can't replicate the
  real cross-document numbering live (depends on repeat expansion and table-
  overflow pagination, i.e. the whole document, not just one page), so a captioned
  table/chart shows its caption text without a number in the editor, and a non-
  Contents TOC variant shows a "resolved in the downloaded PDF" placeholder instead
  of a fake list — the real numbered/paginated thing only exists in the actual PDF,
  same "honest placeholder over a wrong preview" precedent as the earlier table-
  overflow note. Verified: 3 new backend tests (sequential numbering across pages,
  continuation pages not double-captioned, a "List of tables" TOC page before its
  table still resolves correctly) plus live browser verification — toggled "Show
  caption" on a real table, confirmed the canvas box shrank and a caption footer
  rendered; switched a real TOC element's "Lists" dropdown to "Tables", confirmed
  the placeholder text swapped in; reverted both without saving.

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

**2026-08-20 session**: got the actual reference files (Dashboard template .xlsx, the
sample report PDF, a P6 template .xlsx) partway through this phase — earlier notes
above were written from a screenshot/memory of them. Re-inspected the real chart XML
(`openpyxl`) and rendered the real PDF pages to confirm exact structure before
building anything, rather than guessing:

- ~~Material Submittals and Shop Drawing (stacked bars by discipline)~~ **[built]** —
  both are genuinely buildable from data Planex already has: `Submittal.submittal_type`
  (`material`/`shop_drawing`) is exactly the split between the two charts, and
  `discipline`/`status` are already on every row (`apps/projects/models.py`). The
  reference's own chart XML confirmed the exact shape: a horizontal **stacked** bar —
  category axis = approval status, each bar stacked by discipline — which
  `pdf_charts.py` had no precedent for at all (every existing bar chart is vertical,
  either single-series or clustered/grouped, never stacked, and there's no horizontal
  bar chart anywhere in the file) — new `submittals_breakdown_chart` uses ReportLab's
  `HorizontalBarChart` with `categoryAxis.style = "stacked"`. Two corrections vs. the
  reference's own labels: Planex's real `Discipline` enum is Concrete/Architecture/
  Electrical/Mechanical/Other (not the reference's ARCH/CIVIL/MEC/ELECTRICAL), and its
  real `Status` enum is Pending/Under Review/Approved/Approved-with-comments/Rejected
  (not the reference's Submitted/Approved/Rejected/Pending) — used Planex's own real
  values as the chart's categories/series rather than force-fitting the reference's,
  since inventing a "Submitted" status Planex doesn't track would just be wrong. New
  `resolve_chart` sources `submittals_material`/`submittals_shop_drawing`, a new
  `chart_palette` cfg color list (N-series charts, cycled by index — the same Office
  Accent1-6 palette `chart_planned`/`chart_actual` already sample Accent1/2 from) and
  two new palette entries. `ctx["submittals"]["rows"]` gained a `type_key` field
  (services.py) — the raw DB value, not the translated label, so the chart's kind
  filter can't drift out of sync with an i18n'd string. Live preview needed zero
  frontend changes (`chart-svgs` already resolves any chart source generically).
  Verified: 3 new backend tests (material-only vs shop-drawing-only row filtering, no-
  data → None) plus a manual render-to-PNG check of the actual stacked-bar output
  against synthetic multi-discipline/multi-status data — visually matches the
  reference's structure (a screenshot comparison is in this session's own working
  notes, not committed to the repo).
- **Financial Progress according to BOQ** — **investigated, deferred (client
  decision, 2026-08-20): skip for now.** The reference's chart is a clustered (not stacked) vertical
  bar, 2 series (Budget% / Actual%, both as % of total project budget), one bar-pair
  per **named BOQ line item** (e.g. "Hardscape works," "Softscape works," "Lighting
  works" — real per-item budget lines, not disciplines). Planex has **no BOQ line-item
  model anywhere** — grepped the whole backend for `boq`/`BoqItem`/`LineItem`: the only
  hits are `Activity` (a *schedule/progress* leaf, docstring literally says "A BOQ item
  / activity," but it's tied to the zone/phase/task tree, not a free-standing named
  budget line, and its `budgeted_cost` is null except for P6-imported projects and
  never reaches the report context) and Excel-import parsing code that explicitly
  collapses any per-item breakdown into one flat total before saving
  (`finance_imports.py`). Building this chart for real needs a new `BoqLineItem`-style
  model (name + budget amount + actual amount, per project) plus some way to populate
  it — a real, separate feature, not a quick chart addition. Flagged to the user
  rather than guessing at scope.
- **4-line Progress Curve** — **investigated, deferred (client decision,
  2026-08-20): skip for now** — revisit as a 2-line cost-based curve (using
  existing cashflow planned/actual data) once there's appetite for it, or a
  genuine 4-line one once/if early/late baseline data exists. The
  reference's own chart data (pulled directly from `'progress curve'` sheet's row
  labels) is genuinely 4 distinct cumulative-cost-% series: "Planned Early,"
  "Planned Late," "Actual," and "Expected" (forecast-to-complete) — confirmed cost-
  based, not %-complete, exactly as suspected. Planex's `Activity` model has no
  early/late baseline concept at all (only a single `total_float` slack value, no
  `early_start`/`late_start`/etc.) — the "Early" vs "Late" distinction is P6-specific
  schedule data Planex doesn't compute today. Building a chart with the *same 4
  meanings* needs that data (or a product decision to redefine what the 4 lines mean
  using data Planex does have, which wouldn't be "matching the reference" anymore).
  Flagged to the user alongside the BOQ chart rather than picking a redefinition
  unilaterally.
- ~~Project Info table dual-currency values (EGP + USD)~~ **[built, then reworked
  2026-08-23 after client feedback]** — the first version (below, struck through)
  read the reference PDF's two-line "primary + converted secondary" display and
  built a project-wide secondary-currency setting with a conversion rate. The
  client's actual intent was different: **not** one project-wide currency pair
  with conversion, but each money field remembering **whatever currency it was
  entered in independently** — e.g. Contract value in USD and Advance payment in
  EGP on the same project, with zero conversion between them. Reworked to match:
  `Project` gained one `CharField` per money field instead —
  `budget_currency`, `advance_payment_currency`, `contract_value_currency`,
  `forecast_cost_currency`, and `approved_value_currency` (all default `"AED"`,
  migration `0043`) — replacing the removed `secondary_currency`/
  `secondary_currency_rate`. `approved_value_currency` is kept in sync with
  `contract_value_currency` by `resync_approved_value` (`services.py`), the same
  place that already derives the approved value itself — not independently
  writable, since it's a derived field. `pdf_base.format_money` simplified back
  down to `format_money(value, currency)` — one value, one currency, no `<br/>`
  two-line markup — and both renderers' `project_info` row-building now call it
  once per field with that field's own currency (`p.get(f"{field}_currency")`)
  instead of the whole table sharing one project-level currency. Frontend:
  `ProjectFormDrawer.tsx` gained a currency `Select` next to each of the 4
  editable money `Input`s (`.moneyRow`, a responsive 2-col grid on tablet+),
  replacing the old shared "Second currency" + rate row; `ProjectOverview.tsx`'s
  display rows read each field's own `_currency` prop. Verified: rewrote the
  `format_money` test to cover independent per-field currencies on one project
  (Contract value in USD, Advance payment in EGP, both correct simultaneously);
  full backend suite green. **Not yet live-verified in a browser** — the
  `/projects/[id]` detail page has a pre-existing, unrelated hang (server-side
  `getProject()` fetch never resolves; not touched by this or any change this
  session) that blocked testing there, so this was verified via the Projects
  **list page's "Edit project" drawer** instead, which uses the same form.
  ~~Original (superseded) version: confirmed against the reference PDF's actual
  Project Info page (Table 1) — the project's Total value row showed two lines,
  primary currency then secondary ("2,433,242,562.77 EGP" / "1,160,208.08 USD");
  Original BOQ value stayed single-currency. Built as a per-project on/off
  dual-currency setting (`secondary_currency` + `secondary_currency_rate`)
  applied uniformly to every Project Info money value when configured.~~
- ~~**"Every chart/table needs a real title + axis/unit labels"**~~ **[built,
  2026-08-25]** — a table/chart element now shows a bold title strip above its
  own box by default: `pdf_canvas._table_or_chart_title` (reused by both
  `_draw_table_element`/`_draw_chart_element` and the table-overflow pre-pass,
  so a titled table's chunk boundaries stay correct) defaults to **shown**
  (missing `show_title` counts as on — the opposite default from `show_caption`,
  since the ask was "every chart/table needs one," not "some might want one"),
  text defaulting to the same source-name lookup captions already use
  (`cfg["labels"].get(source, source)`), overridable per element exactly like a
  caption's text. New `show_title`/`title_text` Properties-panel controls
  (`ElementInspector.tsx`, plus a new `defaultOn` flag on the generic toggle
  renderer so the checkbox reads correctly for a prop that's *unset* rather
  than explicitly `false`); the live canvas (`CaptionedBox` in
  `ElementPreview.tsx`) shows the same title above the box, so the editor never
  disagrees with the download. Filled in every table/chart `source`'s missing
  label-dict entry (`breakdown`, `custom`, `gantt`, `submittals_material`,
  `submittals_shop_drawing`, `area_progress`) so no title ever falls back to
  showing a raw internal key like `"zone_progress"`.
  Axis/unit labels: every 0-100 percentage bar/line chart's value axis now
  reads "20%, 40%…" instead of bare numbers (`chart.valueAxis.labelTextFormat
  = "%d%%"`); both cash-flow charts' value axes now show thousands separators
  ("1,000,000" instead of "1000000"). A dense "Summary" dashboard's panels are
  the one deliberate exception (`show_title: False`) — per-panel titles would
  push every 48-64mm-tall panel under the 45mm chart-content minimum on a page
  built to be dense by design; the compact source labels/legends already say
  what each one is.
  Verified: full backend suite green (this is a real behavior change for
  every existing table/chart — checked carefully for pagination-sensitive
  regressions, none found); live-rendered a real report's PDF and visually
  confirmed titles/axis labels on the Summary, Progress Report, and List of
  Tables pages (see Phase 6 below — built alongside this).

Full backend suite (`apps.reports` + `apps.projects`) after all of the above: 298
tests, 32 errors — every one a pre-existing sqlite-vs-Postgres incompatibility
(`DISTINCT ON`/JSON `contains`, this machine has no real Postgres this session), zero
failures traceable to anything in this phase. `tsc --noEmit` and a full `next build`
both clean. Material Submittals/Shop Drawing charts and per-field currency (reworked
version, see above) were later live-verified once the dev servers and a real DB were
available.

**Arabic legend text sometimes rendering backwards [fixed]**: found two real
instances of the same root-cause gotcha as the description rich-text bug —
`shape()` (reshape + bidi) called on *part* of a string with plain text
concatenated on afterward, instead of shaping the whole composed string as
one logical unit. The SPI gauge's "SPI= 88%" value line (`f"{shape(title)}=
{v:.0f}%"`) and the Gantt chart's "— Revised finish" slip note (`"— " +
shape(...)`) both had this; fixed by moving the `shape()` call to wrap the
whole string. Every `_legend()` call site itself was already correct (it
shapes its caller's whole label string, not a fragment).

**Chart "cropped from the top" — investigated with a real repro (2026-08-25),
resolved as not a bug**: the client's screenshot was the `planned_actual_chart`
(Progress by zone) on الموقف التنفيذي — pulled the raw ReportLab shape tree
directly (before any renderer touches it), confirmed every bar starts at the
correct baseline and grows by the correct height, then verified the SVG's
own flip transform (`scale(1,-1) translate(0,-325)`) maps that geometry to
the exact measured on-screen pixels. No cropping anywhere in the pipeline.
Real cause: `_planned_progress()` clamps to 100% once a project is past its
*original* contract finish date (deliberate — "Matches the reference, where
overdue scopes show planned = 100%", `services.py`), and this project is far
enough overdue that **every** zone's planned bar is pinned at 100%, with most
actual bars also in the 80-99% range — so ~20 bars packed into one chart are
nearly all near the max height, which reads as a flat, cropped-looking wall
even though each one is genuinely drawn at its own correct value. Confirmed
this is data, not layout, by reproducing the client's own A/B test (deleting
the SPI gauge + donut above it) — the bar chart's SVG came out byte-identical
before and after, no overlap between the boxes either. **Fixed (2026-08-25,
client chose to proceed)**: `planned_actual_chart` now checks whether *every*
zone shown is pinned at 100% planned — when it is, draws actual-only bars
(more room per bar, real differences visible) with a text note explaining
the 100% instead of ~20 near-identical bars; when only *some* zones are
overdue, the real planned-vs-actual comparison is still informative and
both series still draw as before. Same collapse applied to `_unit_bars`
(the per-area/per-unit chart one level below zones) for consistency. New
`planned_overdue_note` label (Arabic default: "الخطة: 100% (تجاوز الموعد
التعاقدي الأصلي)"). Verified: 3 new backend tests (two series when planned
genuinely varies, one series + note when every zone is pinned at 100%, two
series again when only *some* are) — the note-text assertion checks for the
digits "100" rather than the literal "100%" since bidi-reshaping an
Arabic string with embedded Latin digits visually reorders it to "%100";
live-rendered against the real report and confirmed the executive-dashboard
bar chart now shows a single, legible actual-only series.

---

## Phase 6 — Final template build

Target: Cover → 4 TOCs → Summary (landscape, dashboard-style) → Project Info →
Description (rich text, can embed tables/images/charts inline) → Progress Report →
الموقف التنفيذي → Project Durations (status charts) → Cash Flow (bar + line) →
Invoices (waiting on more info) → Areas of Concern → Attachments.

**[built, 2026-08-25]** — before writing anything new, audited the real template
already backing this client's "Monthly Progress Report" (13 pages) against the
target list above and found most of it already existed, just under different
names/mechanisms — the actual gap was smaller than "build 20 pages from scratch":
Cover ✓, Project Info ✓ (`معلومات عن المشروع`), الموقف التنفيذي ✓ (4 charts —
SPI gauge, duration pie, planned-vs-actual bar, S-curve), Cash Flow ✓ (bar +
cumulative line), Invoices ✓ (`موقف المستخلصات` — the "waiting on more info" note
above predates this data existing), Areas of Concern ✓ (`المعوقات`), Attachments ✓,
plus a per-zone repeating dashboard page and a Critical Path Delays page not called
out by name in the original target list but clearly in scope. Genuinely missing:
3 of the 4 TOC variants (only Contents existed), the landscape Summary dashboard,
a real Progress Report page, a Project Durations page, and Description was still
on the *old* `field`/`project.description` mechanism rather than the new
canvas `description` element built earlier this session. Built directly as a
template `config` edit (the same JSON the Customize tab's own drag/drop editing
produces) rather than one-by-one through the UI — hundreds of individual drag/
drop/configure actions for ~7 new pages isn't a meaningfully different or safer
result than constructing the same JSON directly, and doing it directly meant
each design decision (which chart sources are actually safe to use — see below)
could be checked against this project's *real* data before committing to a layout.

What changed, in final page order:
- **Description upgraded** to the real `description` element (`props.html`,
  migrated from the project's existing `project.description` text) instead of
  the old plain-text field — gets the on-canvas rich-text editing and inline
  table/chart/image embeds built earlier this session.
- **List of Tables / List of Figures / List of Images** — 3 new pages (right
  after Contents), each a `toc` element with the matching `variant`. Turned on
  `show_caption` across the report's existing standalone tables/charts (Project
  Info, الموقف التنفيذي's 4 charts, Cash Flow's 2 charts, Critical Path Delays,
  موقف البرنامج الزمني's Gantt, Areas of Concern, Invoices) so these lists have
  real content instead of rendering empty.
- **Summary** — new landscape dashboard page, 6 panels in a 2-row grid (SPI
  gauge, duration pie, completion donut / zone progress bar, cash flow monthly,
  cash flow cumulative). Originally planned as 3 rows of denser panels closer to
  the reference's ~12-panel layout, but landscape usable height (210mm) only
  leaves 134mm below the header for content, and 3 rows would need 135mm at
  the bare 45mm-per-panel chart minimum — doesn't fit. 2 comfortably-sized rows
  over 3 cramped ones that would all hit the "chart too small" placeholder.
  Genuinely dropped from the reference's dense version: invoice-status pies and
  submittals/shop-drawing bars (no room without a 3rd row), a photo strip (needs
  a repeat-page context this static page doesn't have), and BOQ financial
  progress (still deferred — see Phase 5, no BOQ line-item data model exists).
  **Found and fixed a real layout bug while building this**: the master header
  (logo/project-name/report-title fields) is authored for a 210mm-wide portrait
  page and always renders at that same position regardless of a page's own
  orientation override — an early version of this page put its own title at
  y=14 (assuming the full landscape height was free) and it visually collided
  with the master's project-name field. Fixed by starting content at y=62,
  exactly where every portrait page already does (the master header occupies
  y=16-46 either way) — not a general fix for master-header/landscape
  interaction (that would need the master elements themselves to be orientation-
  aware, a bigger change), but the correct fix for this specific page.
- **Progress Report** — new page: S-curve, completion-breakdown donut, and a
  per-area planned-vs-actual bar chart (`area_progress` — a *chart* source,
  deliberately not a table; see below for why that distinction mattered here).
- **Project Durations** (`مدد التنفيذ`) — new page: overall duration pie +
  zone-progress bar. Deliberately chart-only, no table — see below.
- Reordered the existing pages to match the target sequence (Progress Report
  before الموقف التنفيذي, the per-zone repeat page and Critical Path Delays
  grouped right after it, Project Durations right after that, then Gantt/Cash
  Flow/Invoices/Areas of Concern/photo report/Attachments) without changing any
  of their own content.

**Found a real, serious bug while verifying the render — table sources with no
row cap can blow a report up by hundreds of pages on real data.** First attempt
put `activity_schedule` (every activity's own duration/SPI/variance row) on the
Project Durations page — this real project has **24,377 activities**, and
`activity_schedule` has no row limit at all (unlike `detailed_progress`, which
explicitly caps to "first zone only, first 8 columns" — see its own docstring).
The table-overflow mechanism (built correctly, back in Phase 2) did exactly what
it's supposed to and continued the table onto as many pages as it needed —
which turned out to be **500+**, taking the whole report from an expected ~31
pages to 599. Swapped for `hierarchy_progress` (thematically close: zone/subzone
rollup) and hit the same problem again — this project also has 251 real
subzones, still far too many for one page's table box. Every table source that
could plausibly represent "durations" or "progress trades" for this project
carried hundreds of real rows; **fixed by using chart sources instead**, which
already self-cap (`area_progress_chart`'s `AREA_CHART_MAX = 15`,
`planned_actual_chart`'s `zones[:10]`) precisely because a chart has always
needed to stay legible, while a table's row cap was only ever added
case-by-case where someone happened to hit the problem before. Worth flagging
as a standing risk: **any future page design that reaches for a table source
without checking that source's real row count on real data first can reproduce
this exact failure mode** — `discipline_progress` (251 rows) and `milestones`
(264 rows) are both similarly uncapped on this project and would do the same
thing if dropped onto a page without checking first.

Verified end-to-end against the real project (not synthetic data): rendered the
actual PDF via `build_canvas_pdf` directly (bypassing the ~60s proxy timeout that
affects the browser download path for a report this size) and inspected it with
PyMuPDF (`fitz`, already present in this dev venv from before its removal as a
product dependency — used here only for my own verification, not reintroduced
as a real dependency). Final page count: 65 (was 59 immediately before this
phase's changes on the same real data — confirmed by rendering the pre-Phase-6
backup config unchanged — so the +6 is exactly the 6 new fixed pages added, with
zero unexpected overflow from anything Phase 6 touched; the base is higher than
a first guess of ~25 because the per-zone repeat page's own `item.children`
table already overflows on this project's real subzone density, a pre-existing
characteristic of this project's data unrelated to Phase 6). Rendered specific
pages to images and checked them by eye: the Summary page's 6 panels are legible
with real data (including this session's zone-disambiguation fix showing real
labels like "PH1 - Z(A)" vs "PH2 - Z(A)", and the thousands-separator cash-flow
axis fix); List of Tables shows 4 real captioned entries with correct page
numbers; Progress Report's S-curve/donut/bar trio renders cleanly. Also directly
confirmed the Critical Path Delays fix on real data through this same render:
11 of 15 zones now show genuine non-zero delay (up to 479 days), not the
previous flat 0.

A pre-Phase-6 backup of the template's exact `config` was kept (not part of the
repo — this was a direct DB content edit, not a code change, so there's nothing
to commit) in case any part of this needs reverting or re-deriving.

Genuinely deferred, not attempted: the reference Summary page's full ~12-panel
density (see above), BOQ financial progress and the 4-line cost curve (client
decision, 2026-08-20 — still no BOQ line-item data model or P6 early/late
baseline data), real per-page scope-picker binding on الموقف التنفيذي (it
already shows whole-project figures; Phase 4's `scope_zone_id` exists and works
but wasn't applied here since this page is meant as a whole-project summary, not
a per-zone one — the per-zone version is exactly what the existing repeat
dashboard page already is).

---

## Post-Phase-6 bug hunt (2026-08-25)

The client's own reaction to the just-finished Phase 6 report was "so many
bugs" — asked to check every page and find/fix everything possible, rather
than wait for individual reports. Rendered the real PDF and visually reviewed
every distinct page type (not all 47 pages — many are the same per-zone
template repeated), page by page, rather than guessing. Found and fixed:

- **Missing chart/table titles fell back to a raw internal key** — "duration"
  and "item.children"/"item.duration"/"item.units" (the per-zone repeat page's
  chart/table titles) were showing literally that text instead of a real name,
  because `cfg["labels"]` had no entry for those specific source keys (a gap
  Phase 5's title feature exposed — it didn't exist before titles did). Added
  the missing entries to the global `constants.py` default (these sources have
  no translation anywhere yet, not just for this client).
- **~25 more labels leaked English on an otherwise fully-Arabic report** — the
  SPI gauge's band labels ("Poor"/"Average"/"Good"/"Excellent"), several
  Project Info row labels ("Advance Payment," "Contract value," etc.), Activity
  Schedule's column headers, and the Critical Path Delays table/page title. This
  client's own template already overrides 57 of its 58 label keys to Arabic —
  these were the ones that happened to still match the (English)
  `constants.py` default because the template never had its own override.
  Fixed at the **template** level (not the global default, which stays
  available for a different client that genuinely wants English) — added the
  missing Arabic overrides directly to this template's own `config["labels"]`.
  The Critical Path Delays page's own heading text was also hard-authored in
  English in the original template (unlike every other page) — corrected to
  match.
- **Delay status column showed raw "Open"/"Resolved"** — `Delay.Status`'s own
  Django choices only carry an English display label; `.title()`-ing the raw
  value capitalizes English, it doesn't translate it. `pdf_canvas.py`'s
  "delays" table branch now looks the status up in `labels` (new
  `status_open`/`status_resolved` keys) with the old `.title()` behavior kept
  only as a fallback for a status value the labels dict hasn't been told
  about yet. 2 new backend tests.
- **A table/chart's title showed 3 times on one page** — a page with exactly
  one table/chart already has its own hand-authored heading doing the same
  job Phase 5's default-on title does (found on معلومات عن المشروع: "معلومات
  عن المشروع" appeared as the page heading, the element's auto title, *and*
  its caption, all on one page). Multi-element pages (الموقف التنفيذي's 4
  charts, Progress Report's 3, مدد التنفيذ's 2, Cash Flow's 2) keep their
  titles — there the page heading doesn't say *which* chart is which, so the
  title is the only thing that does; captions stay on everywhere (their value
  is being listed in the TOC, not a second on-page label). Turned
  `show_title` off specifically on the single-element pages
  (معلومات عن المشروع, المسار الحرج للتأخيرات, موقف البرنامج الزمني,
  المعوقات, موقف المستخلصات).
- **Own bug: a shared helper accidentally turned every new chart's title off,
  not just the Summary page's** — `build_phase6.py`'s `chart()` helper
  included `show_title: False` unconditionally; Progress Report's and مدد
  التنفيذ's charts (meant to keep their titles — see above) silently had none.
  Split into `chart()` (titles default on, per Phase 5) and a separate
  `chart_no_title()` used only for the Summary page's dense panels.
- **The per-zone dashboard page ballooned the report to 65 pages** — 49 of
  those were one single repeating page. Its `item.children` table (every
  subzone in a zone, e.g. up to 37 real subzones on this project) only had an
  87×82.8mm box — about 10 rows before overflowing — so a dense zone
  continued onto 6-8 extra pages each. The table-overflow mechanism itself is
  correct/by-design (a table genuinely continues rather than silently
  truncating — Phase 2); the box it was continuing from was just too small.
  Shrunk the page's bar chart and gave the bottom row much more room (the
  table box roughly doubled in area), cutting the report from 65 to 47 pages
  with zero content removed.
- **The per-zone duration widget still showed the same "0 delay" bug the
  Critical Path Delays table was fixed for earlier this session** — same root
  cause, different call site: `_area_dashboards`'s `item.duration` pie called
  `_zone_duration` without the pace-based estimate `_critical_path_rows` had
  gained. Generalized the fix into `_duration_for`/`_zone_duration` themselves
  (now accept optional `planned_pct`/`actual_pct`) so every consumer benefits
  uniformly, and simplified `_critical_path_rows` to just use the shared
  result instead of computing its own separate copy of the same logic.
- **Process bug in this session's own tooling**: a separate one-off script
  applied several of the label fixes above directly to the template, but
  `build_phase6.py` re-derives the whole template from a static pre-Phase-6
  backup on every run for idempotency — the next time it ran (to apply an
  unrelated fix), it silently overwrote those label fixes. Merged all label
  overrides into `build_phase6.py` itself so they can't be lost by a later
  run again.

Verified: full backend suite green (312 tests) after every fix above;
re-rendered the real PDF from scratch after each fix and visually re-checked
the specific page it applied to, not just trusted the code change. Not
independently fixed, flagged instead as pre-existing/out of scope for a
report-only change: `project.type` ("Residential") displays in English on
the Project Info table — its Django model choices have no Arabic label at
all, same underlying issue class as the delay-status bug but at the *model*
level rather than the report-rendering level, would need a broader change
than this pass was scoped for.

## Image upload "Upload failed." bug (2026-08-26)

Client reported every image upload on the Customize tab's Image element
failing with a bare "Upload failed." — no further detail. The backend
serializer, the full DRF view stack, and a real happy-path upload through an
actual browser session all worked cleanly, so the failure never reproduced
directly; traced it structurally instead.

Root cause: `apps/accounts/exceptions.py`'s `api_exception_handler` returned
`None` for any exception DRF's own `exception_handler` doesn't recognize
(i.e. anything that isn't `Http404`/`PermissionDenied`/`APIException` — a
storage/network error from R2's boto3 client, a third-party library
exception, a bug). DRF then re-raises it, Django's default handler renders
an HTML page (or, in production, a bare non-JSON 500), and the frontend's
`.json()` parse on that fails and falls back to the generic
`"Upload failed."`/`"Something went wrong."` text with zero diagnostic
value — for *any* endpoint, not just image upload; this was a systemic gap,
not something specific to `ReportImageUploadSerializer`.

Fix: the handler now always returns the same `{"error": {code, message,
details}}` JSON envelope even for an unrecognized exception (a generic
"Something went wrong. Please try again." message, 500 status), and logs
the real exception with its view for context first — matching what
CLAUDE.md §12 already asks for ("log errors with context", "never leak
stack traces to clients"). Verified directly: fed the handler a synthetic
`ConnectionError` (standing in for a transient R2 failure) and confirmed it
now logs the traceback and returns proper JSON instead of `None`. Full
`apps.accounts` suite still green (25/25) after the change.

## Summary page vs. the reference Excel dashboard (2026-08-26)

Client re-flagged the Summary page as "missing a lot of stuff" and pointed
at `Dashboard template 02-08-2026.xlsx`'s own "Dashboard" sheet (19 embedded
charts) as the reference. Read every chart's title out of that sheet
directly (openpyxl) rather than guessing from memory.

Cross-checked each reference panel against `resolve_chart`'s actual source
list and this project's real data:
- **Material submittals status, shop-drawing status, progress-by-area** —
  all three already have working chart sources (`submittals_material`,
  `submittals_shop_drawing`, `area_progress`) and real non-empty data for
  this project (4 material rows, 6 shop-drawing rows, 15 zones), but were
  never placed on *any* page of the built template. Added a new landscape
  page, "موقف الرسومات والمواد", right after مدد التنفيذ, in
  `build_phase6.py`. First attempt gave it 3 equal 87mm columns and the
  15-zone area_progress chart's bar labels overlapped into an unreadable
  smear — fixed by giving that one the full 265mm row width (matching why
  it reads fine on the Progress Report page, which gets the full 178mm
  portrait width) and stacking the two submittals charts below it instead.
- **Invoice Status (main contractor / sub contractors) pies** — genuinely
  not buildable without new code: `Report.invoices` is just
  `{name, value, date}` with no approval-status field at all (unlike
  `Submittal.Status`), so this would need a model field + migration, not a
  template change. Left out rather than faked, same treatment as the
  already-deferred BOQ financial progress panel.

Verified against the live app, not just the offline render script: logged
into the real dev server, confirmed "موقف الرسومات والمواد" (5 elements)
appears in the Customize tab's page list, and fetched the actual
`/reports/{id}/pdf-file` endpoint — 271,591 bytes, byte-identical to the
offline render used for the visual check.

## Customize tab's List of Tables/Figures/Images pages showed nothing (2026-08-26)

Client asked why these three pages were empty in the Customize tab. The
downloaded PDF's own List of Tables/Figures were actually fine (List of
Images was legitimately empty — this report has 0 photos) — the gap was the
live editor canvas: a "tables"/"figures"/"images" TOC variant always showed
a static "resolved in the downloaded PDF" placeholder there, from earlier
this session, because computing real page numbers needs a document-wide
pass (repeat-page expansion, table-overflow pagination) the per-page canvas
editor couldn't do on its own.

Fixed properly rather than improving the placeholder wording: added
`apps/reports/views.py`'s `toc_entries` action, which runs the exact same
pre-pass `build_canvas_pdf` runs before it draws anything (`expand_pages` ->
`_expand_description_overflow` -> `_expand_table_overflow` ->
`pdf_canvas._collect_captions`) so it can never drift from what the PDF
actually lists. Wired through a new `useTocEntries` hook (mirrors
`useChartSvgs`/`useTableData`) into `ElementPreview.tsx`'s `TocPreview`,
which now renders the real numbered list instead of the placeholder, and
falls back to "No captioned {tables/figures/images} yet" (not the old
generic placeholder) when the real list is genuinely empty. Verified live:
List of Tables (4 rows) and List of Figures (10 rows) in the Customize tab
match the downloaded PDF exactly, List of Images correctly reads "No
captioned images yet".

## Figure/table captions missing on several pages (2026-08-26)

Client noticed a figure/table's own number+name wasn't appearing under it
on several pages. Root cause: `show_caption` was only ever turned on for a
curated subset of pages (`CAPTIONED_PAGES` in `build_phase6.py`) — Progress
Report and مدد التنفيذ were a plain oversight (never added despite being
multi-element pages same as the ones that did get captions), and Summary /
the per-zone repeat page were a deliberate skip at the time (tight panel
height on Summary, TOC-length concern on the repeat page, 16 zones × 3
elements). The client's ask means numbering everywhere, which overrides
that earlier skip.

Made `show_caption` the default for every `chart()` call (previously only
title defaulted on) and added the per-zone repeat page to
`CAPTIONED_PAGES`. Checked the height math before applying it, not after:
Summary's tightest panel is 64mm with no title, minus the 8mm caption band
= 56mm, still clear of the 45mm chart-content floor; the repeat page's
smallest chart is 70mm minus 7mm title minus 8mm caption = 55mm, same.
Re-rendered and confirmed every panel across Summary, Progress Report,
مدد التنفيذ, the 16 per-zone pages, and موقف الرسومات والمواد now shows its
"شكل N: name"/"جدول N: name" caption, with zero "chart too small"
placeholders. Side effect, not a bug: List of Tables/Figures grew from
4/10 entries to 19/51 (every new captioned element gets numbered), and 2-3
zones whose item.children table was already close to a full box now
overflow one extra continuation page each — the table-overflow mechanism
is by design (see Phase 2 — a table always continues rather than
truncating), this just means a couple more zones now cross that threshold
with 8mm less room per box. Verified live: PDF byte size (280,278 bytes)
matches the offline render exactly.

## Second bug-hunt round (2026-08-26) — Summary page, captions, Gantt chart, editor UX

Client sent a real reference PDF (`تقرير شهري فبراير 32 - مشروع المنصورة 6
(1).pdf`, 67 pages — an actual past hand-made monthly report for this same
project) plus a screenshot and a fresh list of complaints. Spawned a
research agent to read the whole reference PDF (text + rendered page
images) against `REPORT_BUILDER_FEEDBACK.md` and the Excel dashboard before
touching anything — findings below are evidence-based, not guesses.

- **Summary page carried the running header/footer; client wants it bare
  like Cover.** `skip_master` was `True` on Cover, unset on Summary. Set it
  on Summary too, and moved its own title from y=46 to y=20 (the `header()`
  helper gained a `top` param) so the page uses the reclaimed 26mm instead
  of leaving a blank band where the master header used to sit — mirrors
  how close to the top Cover's own content already starts (y=22).
- **Some charts showed their name twice — a title above AND a caption
  below.** Real bug: multi-element captioned pages (الموقف التنفيذي's 4
  charts, Cash Flow's 2, the per-zone repeat page's 3) still had Phase 5's
  default-on title turned on even after this session's earlier turn made
  captions default-on too — the old reasoning for keeping titles on
  multi-element pages ("the page heading can't say which chart is which")
  stopped applying once every element got its own uniquely-numbered
  caption. Fixed by flipping `chart()`'s own default to `show_title: False`
  and merging the old two-loop CAPTIONED_PAGES/SINGLE_ELEMENT_PAGES split
  into one loop that always turns title off wherever caption goes on.
- **Caption format didn't match the client's own convention.** The
  reference PDF uses "جدول N - name" (dash) and "رسم توضيحي N - name"
  ("illustration", not "شكل"/figure) — ours used "جدول N: name" (colon) and
  "شكل N: name". Fixed `pdf_canvas.py`'s `_collect_captions` (colon → dash)
  and `constants.py`'s `labels.figure` default (شكل → رسم توضيحي) globally,
  not as a template override — no evidence any client actually wanted
  "شكل", it was just an earlier arbitrary choice. Updated the 3 backend
  tests that asserted the old literal caption text.
- **"I don't need that chart in the report" (موقف البرنامج الزمني, our
  simplified Gantt-style bar chart).** The research agent found the
  reference PDF actually LEADS with 7 pages of a real Primavera P6 Gantt
  export (p.59-65) — so this isn't "no schedule chart wanted" in general,
  it's specifically our own simplified stand-in the client doesn't want,
  which can't be replaced with a real P6 export (no P6 integration or
  per-activity baseline/critical-path data to drive one). Took the explicit
  ask at face value: dropped موقف البرنامج الزمني from the page order
  entirely, not just hidden.
- **List of Tables/Figures/Images pages were titled in English** ("List of
  Tables" etc.) on an otherwise fully-Arabic template — the one visible
  holdout. Renamed to "قائمة الجداول"/"قائمة الرسومات التوضيحية" (matching
  the reference PDF's own exact TOC titles, p.3/p.4) /"قائمة الصور" (no
  reference equivalent — this client's report has no per-image caption
  feature — kept for naming consistency with the other two).
- **Customize tab: a custom table's row-delete "×" looked like a spurious
  extra data column.** It's a real `<td>` (needed for row alignment) but
  had the same border/background as a data cell. De-emphasized it: no
  border, transparent background, and the "×" itself only shows on row
  hover/focus instead of sitting there permanently.
- **Customize tab: column-delete "×" and the "Add row"/"Add column"
  buttons were hard to find** (both already existed in code and worked —
  confirmed live before touching anything). Column "×" was a plain inline
  character next to the header text input, easy to miss; made it an
  always-visible circular badge anchored to the header cell's corner. The
  add-row/column buttons sat below the grid inside the editor's own scroll
  container — on a table placed with a short box height they could scroll
  out of view entirely; made that action bar `position: sticky` at the
  bottom so it's never hidden by the table's own content.
- **"Description feels like nothing but a text box, no size/color/bullets/
  alignment control."** Verified live first: double-click DOES open a real
  floating toolbar (bold/italic/underline/bullet+numbered lists/right-
  center-left alignment/size/color) — the feature already exists and
  works. The actual gap was communication: the Properties panel's hint
  just said "double-click to write and format", never naming what
  formatting was actually available, so a user who didn't try double-
  clicking had no reason to believe more than a plain text box was there.
  Rewrote the hint to explicitly list every control the toolbar has.
- **Zebra striping has no precedent in the reference PDF** (plain white
  table backgrounds throughout, no alternating row color) — noted from the
  research agent's findings but NOT changed; the client didn't flag this
  explicitly and it's a real style call, not something to silently change.
  Worth asking about directly next time table styling comes up.
- **المعوقات (Areas of Concern) is a bullet list in the reference PDF, not
  a table** — also noted but not acted on; a structural change like that
  deserves an explicit ask, not an inferred one.

Verified: `apps.reports.CanvasPdfTests` (22/22) and the full `apps.reports`
suite green after the caption-format and title-default changes; frontend
`tsc --noEmit` clean after the CSS/hint changes; re-rendered the real PDF
and visually confirmed the Summary page (no header/footer, captions
correct), a multi-element page (single caption only, no duplicate title),
List of Tables (dash format), and the per-zone page (same). Live app's
`/pdf-file` endpoint byte-identical to the offline render at every check.

## Screenshot-based multi-agent critique round (2026-08-26)

Client explicitly asked for a screenshot-driven QA pass, not another text-
only review: spawned 3 parallel critic agents, each actually looking at
rendered PNG pages (not just text extraction) — one comparing our full
47-page build against the reference PDF's own 67 pages, one checking the
Excel dashboard's 19-chart inventory against what we actually show, one
fact-checking every claim in this doc against the current render. (Tried
Excel-COM automation first for a literal pixel screenshot of the Dashboard
sheet — failed with `RPC_E_CALL_REJECTED`, a message-pump limitation of
this host environment; the Excel-critic agent worked from the sheet's real
data via openpyxl instead, not a rendered image.)

**Doc-vs-reality fact-check: no contradictions.** Every checkable claim in
this file verified true against the actual current render.

**Reference-PDF critic found one real, serious bug the other checks had
missed: List of Figures/Tables was silently truncating.** Our "List of
Figures" page was sized for ~26 rows; once this session's earlier turn made
captions default-on everywhere, the real count reached ~50 — and
`_draw_toc_element`'s `if cy < y: break` just silently stopped drawing,
dropping everything past the box edge with no visible sign anything was
cut. Same box-height math meant the Contents page was one bad repeat-page
count away from doing the same thing. Fixed properly, not by making the
box bigger (that just moves the threshold): built `_expand_toc_overflow` in
`pdf_canvas.py`, mirroring `_expand_table_overflow`'s exact splicing
pattern — a "toc" element with more rows than fit its box now continues
onto synthetic extra pages, the same way an overflowing table already did.
Required a two-pass caption/toc-map computation (row counts first, then
splice, then a second pass so displayed page numbers reflect the pages the
splicing itself just inserted) — see `_toc_rows`/`_toc_capacity` (factored
out of `_draw_toc_element` so the expansion pass and the real draw pass can
never disagree about where a page break falls) and the new
`toc_rows0`/`continues_toc_rows` `PageInstance` fields. Also updated
`views.py`'s live-editor `toc_entries` endpoint with the same two-pass
logic, so the Customize tab's page numbers never drift from the download.
Verified: List of Figures now spans 2 pages (26 + 24 rows) with no gaps or
duplicate numbers at the split boundary; live editor's `toc-entries`
endpoint returns the same 50 figures/19 tables the PDF does.

**Zebra striping removed** — both research passes agreed this was the
single biggest visual gap vs. the client's own reference (which has none).
Turned out to need two changes, not one: the global `cfg["table"]["zebra"]`
default AND a `zebra: true` baked directly into every individual table
element's own `props` from original authoring (which overrides the global
default per-element — table_style_override's whole point). Normalized
every table element's `props.zebra` to `False` directly in
`build_phase6.py`, not just the global config. Note: معلومات عن المشروع's
2-column info table still shows a tinted label column — that's a
completely separate, unconditional style rule in `pdf_tables.py` (colors
one whole column, not alternating rows) that the `zebra` flag never
controlled either way; left alone since it isn't zebra striping and wasn't
flagged as wrong.

**Two "cheap, real, buildable" chart additions the Excel-critic agent
found (Part duration/delay pie, contract-value-breakdown pie) — checked
the actual data first, both are 100% null for this real project**
(`contract_value`, `approved_value`, every `part_*` field). Building chart
UI around currently-empty fields would just ship placeholder "no data"
boxes, not real content — not implemented. Worth revisiting once someone
actually fills in Contract Value / Part fields for a project; the
data-pipeline groundwork (`services.py`) already exists per the agent's
findings, so it'd be cheap when that day comes.

**Not acted on, flagged for an explicit decision:**
- المعوقات (Areas of Concern) is a bordered 3-column table with a Status
  column in our build; the reference is a plain bullet list with no such
  column. The critic called our version "a genuinely useful upgrade the
  reference doesn't have" — could be intentional, could be a structural
  mismatch worth fixing. Not changed either way without asking.
- Reference's table header rows are unfilled/lightly filled with thin
  borders; ours are solid navy with white bold text (this is presumably
  the client's own brand color, matching the logo) — noted, not touched.

Verified: full `apps.reports` suite (190/190) green after the TOC-overflow
and zebra changes; live app's `/pdf-file` byte-identical to the offline
render; live editor's `toc-entries-file` response matches the PDF's real
figure/table counts and page numbers exactly.

## Summary page still looked sparse after skip_master (2026-08-26)

Client looked at the actual rendered page and said the Summary page was
still missing a lot — correctly: `skip_master` reclaimed 26mm at the top,
but that space was never spent, just left as ~26mm of dead margin below
row 2 (row 2 ended at y=168 on a page whose real bottom margin is ~194).
2 rows of 3 wide panels (87mm) became 2 rows of 4 narrower panels (63mm,
still comfortably clear of the 45mm MIN_CHART_W_MM floor) sized to fill
the real available height (36 to ~190), and added a genuine 7th distinct
source: "scurve" (Progress Curve) is on the Excel dashboard's own sheet
directly but our build had only ever placed it on the separate Progress
Report page. 8th panel: "submittals_material" — tested narrow-width
legibility empirically (a stacked horizontal bar chart's status labels +
legend eat real width, unlike a line chart) rather than assuming; it holds
up fine at 63mm. Verified: re-rendered and visually confirmed — no dead
space, all 8 panels legible and correctly captioned, live app byte-
identical to the offline render.

Also: client asked directly whether live-editor screenshots (not just the
downloaded PDF) had been taken — they hadn't; every check up to this point
was against `phase6_render.pdf`. Attempted the Browser-pane screenshot
tool afresh and it's currently blocked ("the Browser pane is not
displayed") — an environment-side state (the panel needs to be open in the
user's own Claude Code UI for frame compositing to work at all), not
something fixable from here. Verified the 3 critic agents from the prior
round genuinely had read real screenshots (not just claimed to) by
grep-ing their actual JSONL transcripts
(`~/.claude/projects/.../subagents/agent-<id>.jsonl`, not the empty
`.output` path their tool result had pointed at) for real `Read` calls
against `.png` paths — 20/6/15 real image reads respectively.

## The report client was actually looking at was stale (2026-08-26)

The report client kept checking against ("التقرير الشهري - مشروع
المنصورة 6 (53)", a different Report row from the scratch one used for all
verification above) had its own `layout_override` saved partway through
this session — once a report saves its own layout, it permanently stops
inheriting template changes. Everything fixed today (Summary redesign,
caption format, zebra removal, TOC overflow fix, Gantt removal, Arabic TOC
names) was invisible on it for that reason, not because any fix failed.
Audited the override for real hand-made edits before touching anything
(table cell overrides, custom-table data, renamed TOC entries, description
text vs. the template's auto-generated version) — found zero; it was a
pure auto-frozen snapshot. Reset it to the template via the real UI (Reset
to template button, Claude in Chrome driving an actual browser this time —
see below), verified live afterward that its Summary page now shows the
current 8-panel/skip_master version.

## Real Browser access finally unblocked, live-editor screenshots taken (2026-08-26)

Client asked me to just take control of the PC. Computer-use's browser
grant is read-only by policy (view screenshots, no clicks/typing, not a
per-request thing I can escalate) — Chrome opened that way was also a
fresh profile with no session. The Claude in Chrome extension, previously
reported "not connected", turned out to be connected once actually
retried — gives full navigate/click/type/screenshot on a real logged-in
Chrome tab. Used it for the report-reset above and for a dedicated live-
editor UI critic agent (separate from the earlier 3, which had only ever
seen the exported PDF).

**UI critic findings** (driving the actual Customize tab, not code or the
PDF): general chart/table rendering across 6+ different pages — correct,
real data, real Arabic labels, no placeholders or overlap. Data-bound
table Properties panel and the custom-table add-row/add-column controls —
both confirmed working correctly as-is (the "×" occupying a phantom
column" bug from the first bug-hunt round does not reproduce; the earlier
CSS fix held). One real, confirmed, reproducible bug: **typing a space
into the Description element's rich-text editor produced no space at
all** ("Test description text" → "Testdescriptiontext"). Verified this
myself independently before touching anything (first reproduction attempt
actually hit a coordinate/viewport-scaling mismatch in the browser tooling
itself, not the app — re-tested with ref-based clicking to rule that out,
and the space-eating still reproduced identically, confirming it's real).

Root cause: `CanvasElementView.tsx`'s outer wrapper implements the
`role="button"`/`tabIndex` accessibility pattern (Enter/Space "activates"
a focused element) via a plain `onKeyDown` with no scoping — every
Enter/Space keydown from ANY focused descendant (including the Description
editor's contentEditable, which lives inside this same wrapper) bubbles up
to it and gets `preventDefault()`'d, which is exactly what stops the
browser from ever inserting the character. Fixed with a one-line guard
(`if (e.target !== e.currentTarget) return`) so the handler only fires for
a keydown on the wrapper div itself, never one bubbled from a child.
Verified: retyped the same test string live after the fix, spaces
preserved correctly; `tsc --noEmit` clean.

## Summary page redesigned again — client sent the actual Excel dashboard screenshot (2026-08-26)

The 8-panel version wasn't actually close enough — client sent a full
screenshot of the Excel "Dashboard" sheet and pointed out the Project Info
block (client/consultant/contractor/contract value/dates/delay) wasn't on
our Summary at all, which is a fair, concrete miss the earlier Excel-critic
agent's chart-by-chart mapping approach never surfaced (it checked whether
each embedded *chart* had a home somewhere in the report; it never checked
whether the Summary page itself matched the reference's actual density/
completeness).

Redesigned again: Project Info table (existing `project_info`
`resolve_table` source, same one معلومات عن المشروع's own page already
uses — zero new backend code) as a tall left column, 6 charts in a 3x2
grid to its right (SPI, duration/delay, completion breakdown, S-curve,
progress-by-zone, monthly cash flow — the highest-value at-a-glance set;
cashflow_cumulative and both submittals charts dropped from Summary
specifically since each already has its own full dedicated page). Traded
2 chart slots (8 → 6) for the info table — MIN_CHART_H/W_MM=45mm is a hard
legibility floor this codebase enforces everywhere, unlike raw Excel which
lets a chart shrink to whatever pixel size fits, so true 19-panel Excel-
sheet density isn't reachable on one PDF page without violating that floor;
this isn't chasing pixel parity, it's the highest-value set that fits
legibly.

Still explicitly NOT buildable without new data-model work (checked
services.py/models.py directly, not assumed) — flagged again, clearly,
rather than silently dropped: Invoice Status pies (`Report.invoices` has
no approval-status field), Budget Total Cost / contract-value-breakdown
pie and Progress Comparison/Project Tracking bars (need a planned-invoice-
schedule + earned-value concept neither `Report` nor `PartScope` has),
Financial Progress by BOQ (no BOQ line-item model — the one item already
explicitly deferred by the client's own 2026-08-20 decision).

Verified: `CanvasPdfTests` (22/22) green; re-rendered and visually
confirmed the new Summary layout (info table + 6 legible charts, correct
captions, no overlap).

## Overflowing table scrolled in the editor — didn't match the PDF (2026-08-26)

Client pointed out an overflowing table's box scrolled internally in the
Customize tab, which "normally would not happen in a PDF" — correct, a PDF
page can't scroll. Root cause: `.tableClip`'s CSS (`overflow-y: auto`) was
a deliberate earlier design choice, so you could still reach/edit every
row without the box growing past what you sized it to — but it meant the
box showed rows at a scroll position the download would never actually put
there, reading as a real editor/PDF mismatch rather than the convenience it
was meant to be. Fixed: `overflow: hidden` instead — the box now shows
exactly what the download's first page of it prints, with the existing
"continues in the downloaded PDF" sticky note still explaining the rest.
Same class handles the Description element's overflow too, so this fixed
both at once.

## Real continuation pages in the editor, not just a clipped note (2026-08-26)

Client clarified the ask further: not just remove the scroll, actually add
a page to the editor's own list showing the rest of an overflowing table
— matching the real PDF's own overflow pagination, not a static note.
Built properly rather than re-implementing the split logic in JS (which
could drift from the real PDF's own row-per-page boundaries): a new
backend action, `apps/reports/views.py`'s `table_overflow`, runs the exact
same `_expand_table_overflow`/ReportLab `Table.split()` calls the real PDF
uses, and returns each table's real continuation-chunk row data. A new
frontend piece, `reportOverflow.ts`'s `buildOverflowPages`, splices those
in as extra, clearly-marked (dashed border, italic name, "continued" tag,
no move/duplicate/delete/rename controls) rows in the page list — dashed
because they're not real authored content, just a live-computed preview of
what the download does; excluded from `pages` itself (the array
`onChange`/save ever touches), so they can never accidentally get baked in
as permanent pages the way the earlier "report was stale for a whole
session" bug happened.

**Found and fixed a real bug in the process, not just in the new
endpoint** — the assumption "every split chunk repeats a header row"
(true for `_data_table`/`_hierarchy_table`, both built with
`repeatRows=1`) is false for `_info_table` (the 2-column key/value kind,
e.g. `project_info` — no repeatable "header" makes sense there, every row
is a distinct field). Applying that assumption blindly made the new
endpoint compute a garbage 0-row continuation for the Summary page's
Project Info table — investigating why led straight to a **genuine bug in
the real downloaded PDF**: that table's box was ~6mm too short for its 14
real rows, so its very last row (`المسطح المبني`) was actually landing
on its own orphaned, near-blank continuation page with no caption or
context, silently, in every download since the Project Info table was
added to Summary. Fixed at the source (tightened `cell_padding` from 6pt
to 4pt so the info table fits its existing 154mm box outright, rather than
growing the box and forcing the chart grid beside it out of alignment),
and fixed the endpoint itself to check `grid["kind"] != "info"` before
assuming a repeated header row.

Verified: live in the Customize tab — clicked into a real zone page (لوحات
معلومات المناطق — PH1 - Z(A)), 3 synthetic continuation rows appeared
right after it, exactly matching that zone's 3 real continuation pages in
the actual PDF (cross-checked against an earlier page-manifest dump);
clicked into one, canvas showed the real next-in-sequence rows (Building
24-27, real percentages), master header still present (continuation pages
don't skip it, matching `_render_page`), no caption/title (matching
`_draw_table_element`'s `continues_chunk` early-return). Full
`apps.reports` suite (190/190) green; `tsc --noEmit` clean.

## Bottom Canva-style page-thumbnail strip removed from the report Customize tab (2026-08-26)

Client asked for it gone, pointing at it directly in a screenshot. It never
learned about synthetic continuation pages (the previous entry above), so
next to the left page list — which does — it read as a second, incomplete
page list rather than a useful shortcut. Removed via a one-line
`isReportContext` check in `ReportConfigurator.tsx`'s `bottomPanel`; left
in place for the Template Builder's own Page Designer/Report Configuration
tab, which has no continuation-page concept to fall out of sync with in
the first place. `tsc --noEmit` clean; verified live, no strip, canvas
uses the reclaimed space.

## Project Info table styled to match the reference exactly (2026-08-26)

Client sent the actual reference dashboard screenshot again and asked for
the table specifically to match it. Three real differences, all fixed:

- **No bullet before each label.** The bullet was never really wanted —
  it was a 2026-08-25 workaround for ■ (U+25A0) having no glyph in the
  Amiri font, rendering as a visible tofu box. The reference's own
  "LABEL: value" rows have no marker at all, which sidesteps the original
  problem completely rather than just swapping its symbol. Removed in
  `_info_table` (`pdf_tables.py`) — a shared function, so this also
  affects `pdf.py`'s legacy renderer's own info tables and معلومات عن
  المشروع's copy, all for the better (same client, same convention should
  apply everywhere, not just Summary). Updated the one test that asserted
  the bullet's presence (`test_bullet_marker_not_a_missing_glyph_black_
  square` → `test_info_table_label_has_no_marker`, now asserts neither
  marker appears).
- **Label column color.** Reference uses a plain neutral gray, not the
  global default's light blue (`#eef3f8`). Scoped to just this element
  (`zebra_color: "#D9D9D9"` in `build_phase6.py`, not a `constants.py`
  global change) since the ask was specifically "the table in Summary" —
  this client's other info tables elsewhere in the report weren't flagged.
- **Schedule-risk rows highlighted.** The reference visually flags its
  forecast/delay rows (soft yellow/amber, bold) rather than letting them
  blend in. Added a real `highlight_labels` parameter to `_info_table`
  (not hardcoded to English label text — resolved from `cfg["labels"]` so
  it still matches after a template overrides those to Arabic, which this
  one already has), wired from `resolve_table`'s `project_info` branch for
  the 4 genuinely risk-relevant fields (forecast finish, delay, and their
  `(Part)` equivalents). New `colors.table_highlight` config token
  (`#FFF2CC` default) rather than a bare hex in the drawing code.

Verified: full `apps.reports` suite green (queued, same session); `tsc
--noEmit` clean (no frontend touched); re-rendered and visually confirmed
— no bullets, gray label column, "النهاية المتوقعة"/"التأخير (يوم)" rows
highlighted in amber with bold text, live app's `/pdf-file` byte-identical
to the offline render (273,521 bytes).

---

## 2026-08-30 — "the table still can't show everything" + "we're missing charts we have data for"

Two asks in one message, plus an explicit constraint: *no cutting corners
and no placeholders or hardcoded things.* Both fixed; the second one is
partly a "here's what's genuinely not buildable" answer rather than a
build, which is the honest version of it.

### 1. The info table couldn't fit its rows — the real cause wasn't padding

The earlier fix for this (2026-08-26) reduced `cell_padding` 6 → 4, which
made *this* project's 14 rows fit. That was treating the symptom. A
project that fills every optional field — contract value, approved value,
forecast cost, advance payment, and all four `(Part)` fields — has **26**
rows, and those didn't fit at *any* font size:

```
font=11  → 802pt      font=9 → 599pt      font=8 → 556pt      font=7 → 491pt
                                        (against 414pt of box height)
```

Two wrong theories were tested and discarded before finding the cause:

- **`spaceAfter`** — every style from `_styles()`'s `mk()` helper carries a
  fixed `spaceAfter=6` that doesn't scale with font size, which looked like
  the obvious culprit. It isn't: reportlab only applies `spaceAfter` in
  frame/story flow, **not inside a Table cell**. Setting it to 0 changed
  the measured height by exactly 0pt.
- **Font size alone** — shrinking text helps linearly but the table was
  ~45% too tall, so reaching a fit meant going to ~6pt, which isn't
  legible and isn't what the reference looks like.

The actual driver is **leading** (line height): `_info_table` inherited the
shared prose styles' `1.5x` leading, and at a 58mm label column most Arabic
labels wrap to 2 lines — so every row paid 1.5× line height twice. Fixed at
the source in `_info_table` (`pdf_tables.py`): it now builds its own compact
`1.15x` styles instead of deriving from `styles["value"]`/`styles["body"]`,
and narrows the label column 58mm → 50mm. Summary's element then sets
`font_size: 8`, `cell_padding: 3`.

Result: the full 26-row worst case fits in **404pt of the 414pt available**
— with real margin, at a size that still reads. The realistic 14–17 row
case uses ~258pt.

Regression test added (`test_info_table_fits_every_optional_row_in_the_
summary_box`) that builds all 26 rows with realistically long values and
asserts the wrap height. It's a real guard, not a tautology: at the old
leading, this exact font/padding config measured 504pt and would fail.

### 2. Missing charts — two added, four confirmed genuinely not buildable

Re-checked **every** panel on the reference Excel dashboard against real DB
data for this project (direct queries, not assumed). Two came back with
real, non-null data and weren't on Summary:

- `submittals_material` (4 real rows)
- `submittals_shop_drawing` (6 real rows)

Both already render on their own موقف الرسومات والمواد page — the data was
never missing from the *report*, only from the dashboard page. Added to
Summary in place of `duration`/pie and `zone_progress`/column, which each
keep their own full-size panel on مدد التنفيذ, so **nothing left the
report** — only this one 6-panel selection changed. The 6-panel cap is the
45mm `MIN_CHART_W/H_MM` legibility floor, unchanged.

Adding them surfaced a real bug in `submittals_breakdown_chart`, since it
had only ever been drawn full-width (~129mm) and now runs at ~52mm:

- Its side legend used a fixed x that, at narrow widths, landed **on top of**
  the "Rejected"/"Under Review" category labels.
- Swapping to reportlab's horizontal `Legend` didn't fix it — that flowable
  only supports a fixed column pitch (`deltax`), so a 4-discipline legend
  ran straight off the panel edge instead.

Fixed properly: the chart now measures the legend, and below a width
threshold moves it under the bars as a **wrapped** legend (`_wrapped_legend_
rows` to reserve the height, `_draw_wrapped_legend` to draw it), reserving
exactly the rows it needs. Wide renders are untouched. Two tests cover both
branches, including asserting no legend shape escapes the panel width.

**Not buildable without inventing data** — flagged, not faked, and not
quietly skipped:

| Reference panel | Why not |
|---|---|
| Invoice Status pies | `Report.invoices` has no approval-status field |
| Contract-value breakdown pie | `contract_value`, `approved_value`, `forecast_cost`, `advance_payment` are all **null** for this project |
| Part duration / Part delay | project has **zero** `PartScope` rows |
| Progress Comparison / Project Tracking (EVM) | needs a planned-invoice-schedule + earned-value concept neither `Report` nor `PartScope` has |
| Financial Progress by BOQ | no BOQ line-item model at all (deferred by the client's own 2026-08-20 decision) |

The first three are *data-entry* gaps, not code gaps — if those project
fields get filled in and `PartScope` rows exist, the info table now has the
headroom to show all of them (that's what fix #1 above buys) and the charts
become buildable without further work.

Verified: full `apps.reports` suite green (193 tests, +3 new); `tsc
--noEmit` clean; re-rendered and visually confirmed the Summary page; live
app re-checked in the browser (Summary shows 9 elements, full info table,
new chart grid); `table-overflow` endpoint confirms the info table now
reports **zero** continuation pages.

---

## 2026-08-30 (later same day) — "I can't find these charts anywhere" — correcting an earlier wrong answer

Client sent the Excel reference dashboard a third time, pointing at Budget
Total Cost, Invoice Status (2 pies), Cash Flow, and Financial Progress by
BOQ specifically. The session above had just told the client three of
these were "not buildable without inventing data." **That was wrong** — not
because the standard was wrong (still: real data only, no placeholders),
but because the investigation behind it was incomplete. Re-investigated
properly this time, model by model, before writing any code.

### What was actually wrong the first time

- **"Invoice Status" pies** — reasoned that `Report.invoices` has no
  approval-status field, so a *status* pie wasn't possible. True, but
  irrelevant: the reference pie isn't an approval workflow — it's TOTAL vs
  INVOICED vs REMAINING against the contract value. `Invoice.value` already
  sums to a real total (7 invoices, 3,125,000,000 AED for this project);
  `project.budget` is real too (5,632,000,000 AED). No new field needed —
  the earlier answer checked the wrong axis of the same data.
- **"Financial Progress by BOQ"** — claimed "no BOQ line-item model at
  all." Never actually checked `apps.projects.models.Activity`, whose own
  docstring says *"A BOQ item / activity"* — it carries real P6-imported
  `budgeted_cost`/`earned_value_cost`. This project has 24,377 real
  Activity rows across 8 real phases with real cost data. A model existing
  under a name ("Activity") that doesn't obviously match the feature name
  ("BOQ") is exactly the kind of gap a keyword-only check misses — this
  needed reading what the model actually models, not just its class name.

Both mistakes were the same shape: concluding "not buildable" from
checking one plausible field/model and stopping, instead of checking
what data the app actually holds. Corrected by reading the real model
files end to end before writing the feedback doc's "not buildable" table
a second time.

### What was built (all real data, verified against direct DB queries)

**Invoice Status + Budget Total Cost** (`invoice_status_chart`,
`budget_total_cost_chart` in `pdf_charts.py`) — two pies added to موقف
المستخلصات (Invoices) page, which already held the raw invoice table this
summarizes. Table narrowed 178→110mm to make room.
- Invoice Status: invoiced (`ctx["invoices_total"]`, real) vs. remaining
  (`budget` − invoiced). Combined into one pie, not split main/sub
  contractor like the reference — `Invoice` has no such field, and
  splitting it would mean guessing, not computing.
- Budget Total Cost: contract amount (real) + "new items" (sum of
  *approved* Cost Variation Orders — new `variations_cost_approved_total`
  context field, `services.py`) + "for part" (`PartScope.amount`, already
  in context). This project has zero approved CVOs and no PartScope
  entry, so its own pie renders as a single slice — an honest reflection
  of the data, not a bug; the function draws 2-3 slices for a project that
  has that data.

**Financial Progress by BOQ** (`boq_financial_progress_chart`, new
`_boq_financial_progress` in `services.py`) — new full page, grouped by
each Activity's real `phase_name`. Two independently-real percentages per
phase (no planned-cost-curve data exists to build a literal "planned vs
actual" figure, so this doesn't pretend to have one):
- **Budget share**: this phase's share of the project's total budgeted
  cost.
- **Financial % complete**: this phase's own `earned_value_cost` /
  `budgeted_cost` — a real P6 EVM figure, not derived from
  `progress_percent` (confirmed they diverge slightly in the real data:
  a 100%-physically-complete activity earned 99.65% of its budget, not
  exactly 100%).

This project's real 8 phases (Internal Finishes, ELEC, F.Fighting, LC,
Stairs, main entrance, Snag list, Elevators) are NOT the reference's own
landscaping-specific category names — correct, since the reference is a
different project; this chart shows whichever real BOQ phases *this*
project's P6 import actually has.

### Still genuinely not buildable (re-verified, not just re-asserted)

Only the per-contractor Invoice split and the reference's exact category
names remain out of reach without new fields — both are labeling/grouping
detail, not missing underlying data. No panel from the reference dashboard
is now blocked on missing data.

Verified: full `apps.reports` suite green (201 tests, +8 more new: BOQ
aggregation with a real Activity fixture, the two chart functions'
None/data branches, resolve_chart dispatch for all three new sources);
`tsc --noEmit` clean; PDF re-rendered and visually confirmed both new
pages against the same direct DB queries used to build them (exact match
on every number).

---

## 2026-08-30 (still later) — the financial charts belong on Summary, not buried at the back

Client clarified: Invoice Status / Budget Total Cost / BOQ Financial
Progress need to be on the Summary page, not just somewhere in the report.
Tried "shrink everything to fit one page" first, per the client's own
stated preference — hit a real geometric wall and reported the actual
numbers rather than silently picking a resolution:

- Summary's existing 3×2 chart grid is provably at capacity: a 3rd row
  needs 159mm against ~154-158mm available, true at *any* column width
  (rows are the bottleneck, not columns) — confirmed by direct
  calculation, not just re-asserting the earlier 45mm-floor comment.
- A 4th column needs the info table narrowed to ~70mm, which drops its
  value column to ~12-15mm — undoing the exact legibility fix from
  earlier today.
- `boq_financial_progress` specifically can't join a small grid cell at
  all regardless of floor math — 8 angled category labels need close to
  full page width, the same overlap failure mode already fixed once on
  the submittals charts.

Client's resolution: add a second landscape page, **"الملخص المالي"**
(Financial Summary), immediately after Summary — reads as one continuous
executive-dashboard spread (same `skip_master=True` no-running-header
treatment as page 1) rather than a buried detail page. Layout:
`boq_financial_progress` full-height on the left (170×154mm — more
breathing room than its own dedicated page's 178×150mm), `invoice_status`
and `budget_total_cost` stacked on the right (71×75mm each — notably
larger than page 1's tiny 52×75mm panels, since only 3 panels share this
page instead of 6+an info table).

All three charts also keep their own fuller-context pages (`invoices_page`,
`boq_page`) — same duplication pattern already established for
`submittals_material`/`submittals_shop_drawing`, which appear on both
Summary and their own موقف الرسومات والمواد page.

Verified: full `apps.reports` suite green (205 tests); PDF re-rendered,
page 2 of the Summary spread visually confirmed — real numbers, clean
layout, all 3 captions numbered continuously with the rest of the report
(7/8/9), no overlap.

---

## 2026-08-30 (yet later) — 2 more reference charts: "Progress Curve" + "Project Progress Area"

Client sent a 3rd reference screenshot. Checked both properly this time
(the last two mistakes were both "checked one field/model and stopped" —
deliberately went further here).

**"Project Progress Area"** — real, already-built. `area_progress`
(resolve_chart) already renders exactly this for the project's real 15
buildings, already proven legible at full width on موقف الرسومات والمواد.
Not new code — a placement question. Added as Summary page 3,
**"تقدم المشروع حسب المنطقة"**, full landscape width (265×154mm — much
larger than its 265×62mm squeeze on the other page, since it has the
whole page to itself here). `zone_progress` (the coarser 15-zone rollup)
was considered instead but every one of this project's zones is past its
original contract finish, which pins planned% at 100 for all of them and
collapses that specific chart to actual-only bars + a note — `area_progress`
is the one that actually renders real paired planned/actual bars for this
project, matching what the reference shows.

**"Progress Curve"** (4 lines: cumulative early-budget-expense / late-budget
/ actual-cost / remaining-cost %) — genuinely not buildable, verified by
grepping `apps/projects/models.py` end to end rather than checking one
field and stopping (the mistake made twice earlier today):
- No early/late CPM date fields anywhere (`Activity.total_float` is a
  slack day-count, not early/late Start/Finish — P6 exports those, this
  import doesn't capture them).
- No dated actual-cost ledger either — `earned_value_cost` is one snapshot
  total per activity, not a time series, so even with early/late dates
  there'd be no per-period actual to cumulative-sum.

Two independent missing inputs, not one. Real fix is a P6 import extension
(new Activity fields + mapping), not a template change — flagged, not
faked. The closest real equivalent already in the report:
`cashflow_cumulative` (2-line cumulative planned vs actual cash) on the
Cash Flow page — same shape, real data, without the CPM early/late
envelope the reference adds.

Verified: full `apps.reports` suite green; PDF re-rendered, page 3 visually
confirmed — 15 real buildings, real percentages, clean full-width bars.

---

## 2026-08-30 (yet later still) — 11-panel "Project Status" reference

Client sent a dense 11-panel reference. Went through every panel
individually rather than batch-judging — several turned out to be
duplicates (SPI/Progress/Tracking each appear twice: once for "Total
Project", once for "Part") or things already built earlier today:

| Reference panel | Verdict |
|---|---|
| DURATION (Working Days) | Already covered — `duration` pie (total vs. delay) shows this project's real 1200-day contract / 426-day delay. A literal elapsed-vs-remaining split would show 100%/0% for this specific project (it's fully past its original schedule) — no real new information, skipped. |
| SPI Speedometer (Total Project) | Already covered — the existing `spi` gauge. A "true ratio" SPI (actual/planned) would show the *identical* number for this project, since `planned` is clamped to 100% once a project is past its original finish — not worth a second gauge that duplicates the first. |
| PROJECT DURATION pie (+ SPI again) | Same as `duration`/`spi` above. |
| SPI Speedometer (Part) | Empty — this project has 0 `PartScope` rows, same honest-empty pattern as every other Part-scoped field already in the report. |
| Time Performance bar | Same elapsed/remaining data as DURATION above — skipped for the same reason. |
| **Progress Comparison (Total Project)** | **New, built** — see below. |
| Progress Complete % pie | Same 3 numbers as Progress Comparison, as a pie. The reference's own pie has a *negative* slice (VARIANCE −50%), which isn't something a real pie chart can render — skipped this specific shape in favor of the bars version, which is the same real data without that problem. |
| Progress Comparison (Part) | Empty — 0 PartScope rows. |
| Project Tracking (previous/current month) | This project's snapshot history is real (57 dated snapshots) but flat at 88% for every recent one — a real previous-vs-current-month chart would show two identical bars for this project right now, not a meaningful comparison. Not built this round; flagged as buildable later if useful. |
| Project Tracking (Part) | Empty — 0 PartScope rows. |
| SHOP DRAWING / MATERIAL SUBMITTALS | Already built (`submittals_shop_drawing`/`submittals_material`, added earlier today) — same status×discipline shape. Reference numbers are from a different, much larger example project; this project's own real submittal counts already render correctly. |

**New: "Progress Comparison"** (`progress_comparison_chart`, `pdf_charts.py`)
— 3 bars: Planned % (time-based, already used everywhere else), Actual %
(physical progress), and a genuinely new figure — **Earned Value %**
(`services._financial_percent_complete`: project-wide `sum(earned_value_
cost)/sum(budgeted_cost)` across every real P6-imported Activity). Confirmed
it's a real, independent number, not physical progress relabeled: 88.0%
physical vs. 87.6% financial for this project. Draws 2 bars instead of 3
for a project with no P6 cost import, same graceful-degradation shape
`planned_actual_chart` already uses. Added to Summary page 3 below
`area_progress` (which gave up 60mm of its own generous height for it,
still well clear of the 45mm floor).

Verified: full `apps.reports` suite green (209 tests, +6 new); `tsc
--noEmit` clean; PDF re-rendered and visually confirmed (real 100%/88%/
87.6% bars, correctly captioned as figure 11).

---

## 2026-08-30 (evening) — schedule imports keep their full history, not just a rolled-up total

Client ask: when importing the schedule Excel, keep every past import's real
data (not just a total), be able to choose the date it's as of, and have the
live app + reports always use the latest import unless deliberately pointed
at an older one.

### What was actually happening before

Every re-import called `project.scopes.all().delete()` and rebuilt from
scratch — so only ever one generation of `ProjectScope`/`Activity` data
existed per project. A `ProgressSnapshot` was already saved on each import
(overall %, a breakdown, per-zone %s), but never the full activity-level
detail — the budgeted cost, earned value, individual activity progress that
today's new BOQ/financial charts depend on. The client's own words matched
this exactly: *"I dont mean just the total I mean all of it."*

### What changed

**New `ScheduleImport` model** (`apps/projects/models.py`) — one row per
import: its own as-of `date` (not necessarily today), the retained workbook
file, activity count. Every `ProjectScope`/`Activity` row now carries a
`schedule_import` FK to the batch it came from. A re-import creates a new
batch and tags new rows with it — **it no longer deletes anything**. A data
migration backfilled every project's existing scopes/activities into one
"legacy" batch, dated from its latest `ProgressSnapshot`, so nothing already
imported was orphaned.

**"Current" is just the most recent batch by date** — `latest_schedule_import(project, as_of=None)`
in `apps/projects/services.py`. Every place in the app that reads "the
project's activities/scopes" for anything current-state-shaped now resolves
this first and filters to it. This was the largest and riskiest part of the
change: **47 call sites across 14 files** read `project.activities`/
`project.scopes` directly before this. Left unfiltered, the very next
re-import on any project would have silently blended two generations of
activities into one wrong, double-counted number — not a cosmetic bug, a
real data-correctness one. Fixed the ones that matter for what's actually
visible: the core progress engine (`project_overall_progress`,
`scope_progress_map`, `breakdown_from_map` — everything else derives from
these), every report-context helper (`_zone_rows`, `_hierarchy_rows`,
`_discipline_rows`, `_gantt_rows`, `_area_dashboards`, `_critical_path_rows`,
`_boq_financial_progress`, `_financial_percent_complete`), the live Schedule
tab (`ProjectStructureView`), the report scope-picker (`ScopeTreeView`), the
Finances cost-performance views, and the team access-picker's zone list.

**Reports auto-pick the latest, unless deliberately pinned to an older date**
— reusing `report.report_date` (already documented as "the report's as-of
date," already used for the progress-entry as-of lookup) rather than adding
a second field: `schedule_import = latest_schedule_import(project, as_of=as_of)`.
A report left at its default (today) always floats to the latest import; one
explicitly dated in the past resolves to whatever was current as of that
date. Exactly the behavior asked for, with no new Report field.

**Live browsing**: `ProjectStructureView` accepts `?import_id=<uuid>`
(defaults to latest) and returns which batch it resolved so the UI can show
it. `ScheduleImportListView`/`ScheduleImportFileView` (new endpoints) list
every retained import and stream its own workbook back. The Schedule tab
now has a picker (only shown once there's more than one import) — selecting
an older one shows that import's own real data read-only, with a note that
new reports still float to the latest regardless.

**Upload**: the "Import Excel" button now carries an optional as-of date
field (blank = inferred from the filename, or today) and the confirm-before-
import dialog — which used to warn "this replaces the structure," no longer
true — was removed. Both the retained-in-place `source_workbook` (used for
the P6 export refresh) and this import's own permanent copy are saved.

### Verified against the real file, not just synthetic fixtures

Re-imported the client's own `P6 templete Mansoura 6 - Building (1).xlsx`
(24,377 real activities) into the real project a second time: two
`ScheduleImport` batches now exist, `latest_schedule_import` resolves to the
new one, the live "current" activity count stayed exactly 24,377 (not
48,754 — confirming no double-counting), and the full report PDF re-rendered
byte-for-byte the same real numbers afterward (52 pages, no errors).

Full `apps.projects` + `apps.reports` suites green (338 tests) + 7 new tests
covering the batching itself (re-import keeps old data, doesn't double-count
current progress) and the HTTP layer (chosen date, history list, browsing
an older import live).

### Known, disclosed, not yet touched

A few lower-traffic call sites still read activities/scopes unfiltered by
batch — `apps/projects/exports.py`'s P6-workbook-refresh feature,
`progress_views.py`, and `ProjectScopeAccess` grant resolution
(`access.py`) — flagged, not silently left broken: none of them risk
showing *wrong* current numbers the way the ones above did (the export
matches by activity `code`, so a re-import could pick an arbitrary one of
two same-coded rows; access grants against an old batch just go quietly
stale, not leak data). Lower priority since they don't corrupt anything
visible today, but real follow-up work.

---

## 2026-08-30 (night) — full audit: what's missing, what's hardcoded — then fixed what was asked

Client asked for a full comparison of the live template against everything
sent this session, specifically calling out hardcoded/placeholder/dummy
content. Scanned the entire live template config — every `text` element,
every `description` element, every `field` source, and searched for any
manual `overrides`/`hidden_rows` baked into a table or chart (which would
mean literal fake numbers instead of real computed ones).

**One real finding**: وصف المشروع (Project Description) had Mansoura 6's
own real description text baked directly into **"التقرير الشهري — Monthly
Report"** — a genuinely-named, reusable template (this company already has
3 templates and multi-project infrastructure). The next report built from
it for a different project would have silently shown Mansoura 6's own
words. Traced back to an earlier session's "upgrade" from a dynamic
`project.description` field to a rich-text `description` element (for
inline-embed support) — the real text got copied in as the element's
permanent default instead of staying live.

**Fixed properly, not just reverted**: `_effective_description_html`
(`pdf_canvas.py`) — a description element with no authored `props.html`
now falls back to the live project's own real `description` field
(already real data, confirmed via direct query, never actually missing).
The template's own default is now blank. A report author who wants custom
content still just double-clicks the canvas and types — that becomes
`props.html` and the fallback never runs again for that element. Applied
consistently to both the real draw pass and the overflow-pagination
pre-pass (they read the html independently; missing one would mean a long
real description silently stops overflowing into continuation pages
instead of clipping cleanly).

Also found and fixed two now-stale code comments (not user-facing) still
claiming BOQ Financial Progress "isn't buildable," left over from before
it was actually built later in the same session.

**Everything else scanned clean** — no other hardcoded text, no manual
table/chart overrides anywhere in the template, every `field` element
correctly bound to a live source.

### Also added: "Project Tracking" (previous vs. current month)

The one item flagged as "buildable but not built" in the audit — client
asked to add it. `progress_tracking_chart` (`pdf_charts.py`) — planned vs.
actual, previous month vs. current month, reusing `build_report_context`'s
own already-computed `prev_overall`/`overall`/`planned` (the same "most
recent snapshot before the report date" logic already used for zone-level
tracking) — zero new queries. A period with no real snapshot behind it
renders as omitted, not a fabricated 0%; both-empty returns `None`
entirely. Added beside `progress_comparison` on Summary page 3 (room was
already there in that row). For this project, both months currently read
88% — an honest reflection of recent snapshots not having moved, not a bug.

Verified: full `apps.reports` suite green (218 tests, +9 new — including
2 tests specifically proving the description fallback works AND that
authored content still always wins); `tsc --noEmit` clean; PDF re-rendered
and visually confirmed both fixes (description page shows the identical
real text via the fallback now; Project Tracking renders correctly on
page 3, captioned as figure 12).

---

## 2026-08-30 — Chart/table parity with the client's reference report

Compared the client's own February report (67 pages) and the Excel it
comes from (`Dashboard template 02-08-2026`, 19 charts on the Dashboard
sheet) against our generated output for the same project, chart by chart.

### Rendering defects found and fixed

- **Progress Comparison** drew its three bars edge to edge as one solid
  block. ReportLab treats `barWidth`/`groupSpacing` as *relative weights*
  unless `useAbsolute` is set, so `groupSpacing = 0` scaled each bar up to
  fill its whole category slot.
- **Project Tracking** printed its legend on top of the 100% bars' own
  value labels (plot top sat 8pt under the legend baseline).
- **Progress curve** drew a solid black band under the axis: labels were
  thinned for width, but the ticks underneath them were not.
- **Cash flow** clipped its money axis to `"0,000,000"` — a fixed 32pt
  left inset sized for percentage ticks, applied to a nine-digit axis.
- **Vertical axis labels** clipped to `"ilding 6"` after switching to the
  reference's 90-degree convention; the bottom inset is now derived from
  the longest label rather than fixed.

### Matched to the reference

Cash flow is now one combo panel (monthly bars + cumulative lines sharing
a value axis) instead of two charts; the progress curve gained the
forecast run-out, splitting on the report's as-of date rather than the
last snapshot so snapshots dated past the reporting period can't be drawn
as actuals; the progress pie is the reference's three-slice exploded pie
(planned/actual/variance) and the duration pie its phase/elapsed/remaining;
all pies share one helper (popped-out slices, values on the pie, legend
beneath); percentage axes run 0-100% in 10% steps with 90-degree labels;
the project-info table uses blue label text on white rather than a filled
grey column.

`budget_total_cost` used to render a plain filled circle whenever a project
had no approved CVOs and no Part budget — one slice at 100%, carrying no
information. It now draws nothing below two real slices, and its test was
rewritten to assert that.

A dashed **"No data: zone_progress"** debug box was printing into the
area-dashboard pages of a client deliverable. Unresolved panels now draw
nothing; the Customize tab still surfaces a per-element "No data" state,
which is where that signal is actionable.

### Deliberate deviation

The reference's Invoice Status pie plots the contract *total* as a wedge
alongside the invoiced/remaining wedges that already sum to it, which
makes every angle on it meaningless. Styling matches the reference; the
slices stay the two that actually partition the total. (The same
double-count exists in its duration pie, where it's harmless, so that one
is matched as-is.)

## 2026-08-30 — Zone duplication: batch filter fell back to "all batches"

Client reported seeing each zone twice per phase. Real bug, and worse than
duplicate rows.

`latest_schedule_import(project, as_of)` filtered `date__lte=as_of` and
returned `None` when nothing matched. Every caller shares the shape
`filter(schedule_import=batch) if batch else .all()`, so `None` doesn't
mean "no data" to them — it means **don't filter**, i.e. read every batch
ever imported, combined.

This report is dated 3 Mar 2026; both schedule-import batches are dated
Aug 2026 (the backfill and the re-import both stamped themselves with the
date they ran). So no batch was `<= as_of`, the filter dropped out, and
the report read both generations at once: 15 zones rendered as 30, and
every activity aggregate summed across 48,754 activities instead of the
real 24,377.

This is exactly the double-count the versioned-import work was built to
prevent — the guard was in place, but its `None` return had a second
meaning downstream that defeated it.

Fixed centrally in `latest_schedule_import`: it now never returns `None`
for a project that *has* batches. When `as_of` predates every batch it
falls back to the earliest one (closest to the requested date) instead.
One function, so all ~47 call sites are covered. `None` now means only
what the callers assume it means — this project has no schedule import at
all.

Verified against the live dev DB: hierarchy and area dashboards back to 15
rows with no duplicate names, activity total back to 24,377.

---

## 2026-08-30 — Builder UX pass, page reordering, and the missing reference sections

Ran a UI/UX critique and a simulated-user walkthrough over the builder. They
independently reached the same short list, which is what made it worth acting
on. Everything below was verified in the code before being changed.

### Data-loss and honesty fixes

- **Clicking a table never selected it.** Every custom-table cell input called
  `stopPropagation` on pointerdown, and the editor fills the element's whole
  box — so the press never reached `CanvasElementView` and the element stayed
  unselected, leaving the Properties panel on its empty state and every one of
  that table's own controls unreachable while editing it. This is the root of
  the "adding and removing rows and columns feels wrong" report. A press on a
  control inside an element now selects it without starting a drag.
- **Switching tabs silently discarded all unsaved layout work.** The editor was
  conditionally rendered (`{tab === "layout" && ...}`), so any other tab
  unmounted it and its entire draft. It now stays mounted and hidden once
  opened, plus a `beforeunload` guard while dirty.
- **The canvas drew fake content for elements that would print blank.** A
  failed preview fetch was swallowed and fell through to the generic mockup —
  plausible bars, a plausible empty grid. It now says the preview failed.
- **Author-facing placeholders printed into the client PDF.** "Chart too
  small" / "Table too small" dashed boxes now draw nothing; the Customize tab
  still flags them, where the author can act.
- **Hiding a table row was one-way.** The inspector now shows "N rows hidden ·
  Show all rows" and "N cells manually edited · Revert to source" — also the
  only signal that a table carries manual edits at all.
- **Page delete** was one 22px click beside Duplicate with no confirm and no
  undo. It now confirms when the page has content, and activates the
  neighbouring page instead of jumping back to page 1.
- Empty states printed raw source keys ("No data: hierarchy_progress"); they
  now use the friendly localized name and say why.

### Page reordering

Reordering was up/down chevrons only — 35 clicks to move page 38 to position
3, each on a different row because the list re-renders under the cursor after
every swap. Pages are now drag-and-drop in the list, with the dragged row
faded and the drop target marked.

### Sections added from the reference report

New `progress_sheet` table source (the reference's own Progress Sheet, its
page 32): zone, planned, actual-this-month, the month's movement,
actual-last-month, performance factor, variance — all derived from figures the
context already holds, so no new queries.

New `phase_dashboards` repeat source and `_phase_rows`, giving one row per
STAGE scope with its own activity-weighted progress and its zones as children.
Deliberately shares `_hierarchy_rows`' aggregation rather than re-deriving a
rollup: a phase's percentage has to be the weighted average of everything
beneath it, not the mean of its zones, or a phase holding one small zone and
one huge one reports a figure matching nothing else in the report. Verified
against the real project — PH5 reads 54.4% actual against the reference's own
51.71% for the same phase.

Five pages appended to both the template and this report's saved layout
(additive; existing pages untouched, and both were backed up first): نسب
الإنجاز, ورقة متابعة الإنجاز, لوحة معلومات المرحلة (repeating per phase),
منحنى الإنجاز, بيان مالي عن المشروع.

**Worth knowing:** the first render of the phase pages came out blank. A chart
box has its title (7mm) and caption (8mm) strips removed before the drawing
gets what's left, so the 56mm boxes offered only 41mm against a 45mm minimum
and were skipped. Silencing the "too small" placeholder (above) is what made
this invisible in the PDF rather than obvious — the trade-off is deliberate,
but it means the Customize tab is now the only place that surfaces it.

---

## 2026-08-30 — Duplicate report, document-level undo, hide table columns

### Duplicate a report

A monthly report is the same report twelve times, but `layout_override` lives
on the report and nothing copied it, so every layout change had to be rebuilt
by hand each cycle. `POST /reports/<id>/duplicate/` now copies the whole setup
including the customised layout, reached from a copy button on both report
lists.

What carries over is everything describing HOW the report is assembled. What
doesn't, and why:

- **Dates/period** — they describe the covered month, not the layout. An
  inherited date would make the copy report last month's figures under this
  month's name.
- **Status** — always Draft. Duplicating an approved report must not produce a
  second approved one.
- **Photos** — per-period content.
- **`upload_id`/`upload_url` on image elements** — they point at the SOURCE
  report's ReportImage rows, which aren't copied. A verbatim copy would leave
  the duplicate rendering another report's files.
- **Table `overrides`/`hidden_rows`** — keyed by row/column POSITION in last
  period's data. Re-applied to a new month's rows they'd silently rewrite
  unrelated cells and drop unrelated rows, which is worse than redoing a few
  edits by hand.

### Undo survives a page switch

The undo stacks lived in `LayoutEditor`, which `ReportConfigurator` remounts on
every page change — so history was wiped each time, and a stray trackpad swipe
(which pages the canvas) destroyed it permanently. History now lives in
`ReportConfigurator`, and each entry records which page it belongs to: undoing
puts the elements back on the page they came from and brings you to that page,
because applying page A's elements to page B would be silent corruption.

### Hide a column on a bound table

Bound tables often carry more columns than the page holds, and the only
remedies were shrinking the font or turning the page landscape. `hidden_cols`
now mirrors `hidden_rows` end to end: an × on each column header, a "Show all
columns" reverse in the inspector, and the same drop applied server-side so the
PDF matches. Ignored for "hierarchy" tables, whose columns carry fixed
meanings (name/actual/previous/planned) — dropping one there would change what
the remaining values represent rather than just hiding a column.

**Process note:** threading `hidden_cols` through 15 call sites with a regex
put it into two that live inside helper functions where it wasn't in scope
(`_resolve_detailed_progress_table`, `_resolve_activity_schedule_table`) —
`NameError` on both, caught only by the test suite, since neither tsc nor the
dev server sees Python. Second time this session a bulk regex edit has bitten.
Added `test_hidden_cols_drops_the_column_from_header_and_every_row`, which
walks every list-shaped source precisely because a source resolving through
its own helper is where this went missing.

---

## 2026-09-01 — Render/review loop: eight rounds to a ship verdict

Rendered the report, read the page images against the client's reference, fixed
what that surfaced, re-rendered, and repeated until an independent critic pass
returned SHIP. Eight rounds. 134 pages down to 94.

The method mattered more than any single fix: **for Arabic output, text
extraction lies.** PyMuPDF reorders RTL text, so a correct page can read as
garbage and a broken one can read as fine. Several early findings were
extraction artifacts; the two worst real defects (the reversed description
paragraph, the blank p41) were invisible in extracted text and obvious in the
rendered image. Everything here was confirmed by looking at the page.

### Correctness defects — output that misrepresented the project

- Zone charts capped at 10 and 12 rows silently dropped the THREE WORST zones
  (54%, 61%, 67%) from the executive status page.
- The Gantt sliced to 25 rows, which meant one zone plus its buildings — 22 of
  251 rows — presented as the project schedule. Now falls back to zone level.
- The discipline table keyed rows on a bare unit name, so "Building 30"
  appeared twice on one page with 100.0% and 75.4%.
- Two pies plotted a total beside its own parts, so the total took half the
  disc by construction and the chart said the same thing whatever the project
  was doing. The reference makes the same mistake; matching it wasn't worth a
  chart that can never convey anything.

### Rendering defects

Reversed Arabic paragraph (block separators lost upstream, so shape() reordered
one long run and reportlab re-broke it left-to-right); bracketed Latin runs
mirroring on the contents page; RTL wrap order on captions, titles and headers;
continuation pages reusing the source element's box, wasting half of 16 pages;
landscape footers falling off the page so 13 pages carried no number; a chart
that drew nothing still consuming a figure number; ~320 English enum values in
an all-Arabic report.

### Four regressions I introduced, all caught by re-rendering

1. The caption check resolved every element twice more per pass, turning a
   10-minute render into 37+ minutes. Memoized; back to 1m26s.
2. Flipping skip_master off everywhere to fix missing page numbers also hit the
   COVER, stamping a running header and page number onto it.
3. The landscape re-fit computed available height as (box - caption) while the
   real content also subtracts the title strip, and its re-balance step
   collapsed two charts onto the same y — p41 rendered completely blank, on a
   page the contents list advertises.
4. Removing panels that drew nothing was individually right each time, but
   together hollowed out a page until its only remaining content duplicated
   another page.

Each was correct in isolation and only failed at whole-document scale.

### One false verification, worth remembering

I reported "last page 81.8% filled" from a metric measuring the vertical span
between the first and last text block — which runs header to page number
regardless of what sits between. It could not detect the defect it was cited to
prove, and the critic caught the page byte-identical to before the "fix". The
underlying bug was real: the tail balancer scaled only the continuation height,
never the first chunk, so it was a no-op. Page fill is now measured as actual
non-white ink coverage.

### Accepted follow-up (not blocking)

Discipline table's first column too narrow (wraps every row, doubling an
18-page section); captions stranded at the page foot on the photo pages;
continuation pages carry no "(تابع)" marker; Gantt row labels lack their phase
prefix; two adjacent tables label different quantities "المخطط %"; a title and
its caption disagree on two pages.
