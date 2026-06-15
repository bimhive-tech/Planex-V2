# Planex Design System — `style.md`

A design-style reference for generating UI consistent with the Planex product (a clean, professional enterprise SaaS for construction project reporting). Feed this to an AI when you want it to build screens, components, or pages that match this look.

> **Design personality:** Calm, professional, content-first enterprise SaaS. A single indigo-violet accent against a neutral gray/white canvas. Soft shadows, generous whitespace, outline icons, pill-shaped status badges. Nothing decorative competes with the data.

> **Note on hex values:** Colors below are sampled visually from the reference mockups and are accurate to within a few shades. Treat them as authoritative tokens, but feel free to round to the nearest values in your own palette (e.g. Tailwind's `indigo`/`slate` scales are a close match).

---

## 1. Color Palette

### Brand / Primary
| Token | Hex | Usage |
|---|---|---|
| `--primary` | `#5B4FE9` | Primary buttons, active nav, logo mark, links, selected states |
| `--primary-hover` | `#4A3FD0` | Hover/pressed state for primary buttons |
| `--primary-soft` | `#EFEDFE` | Light lavender fill for active nav item, selected backgrounds, primary-tinted icon chips |
| `--primary-text-accent` | `#534AB7` | Headings/links inside document content (slightly muted violet-blue) |

### Neutrals (the workhorses)
| Token | Hex | Usage |
|---|---|---|
| `--bg-canvas` | `#F6F7F9` | App background behind cards |
| `--bg-surface` | `#FFFFFF` | Cards, sidebar, header, inputs, table |
| `--border` | `#E8EAED` | Card borders, dividers, table row lines, input borders |
| `--border-strong` | `#D6D9DE` | Hover borders, stronger separators |
| `--text-primary` | `#1E2430` | Headings, primary body text, table values |
| `--text-secondary` | `#6B7280` | Subtitles, descriptions, labels, secondary metadata |
| `--text-muted` | `#9CA3AF` | Placeholders, timestamps ("Updated 2 days ago"), disabled text |

### Status / Semantic (badges use *light fill + saturated text*)
| Meaning | Text | Fill | Used for |
|---|---|---|---|
| Success | `#1E7E4F` | `#E4F6EC` | "Published", "Approved", "Submitted" |
| Warning | `#B45309` | `#FCF0DF` | "Draft" |
| Danger | `#B42318` | `#FDECEA` | "Shared" stat icon, destructive actions |
| Info | `#1D6FB8` | `#E7F1FB` | Informational tags (optional) |

### Accent set for icon chips (stat cards)
Each stat card uses a soft-tinted square icon chip:
- Indigo `#5B4FE9` on `#EFEDFE`
- Green `#1E7E4F` on `#E4F6EC`
- Amber `#B45309` on `#FCF0DF`
- Coral/Red `#B42318` on `#FDECEA`

---

## 2. Typography

- **Font family:** `Inter`, then `-apple-system, "Segoe UI", Roboto, sans-serif`. A humanist geometric sans — Inter, Plus Jakarta Sans, or SF Pro all fit.
- **Numerals:** Use tabular/lining figures for stats and tables.

| Role | Size | Weight | Color | Notes |
|---|---|---|---|---|
| Page title | 24–26px | 700 | `--text-primary` | e.g. "Templates", "All Reports" |
| Page subtitle | 13–14px | 400 | `--text-secondary` | One line under the title |
| Section / card title | 15–16px | 600 | `--text-primary` | Card headings, panel titles |
| Stat number | 24px | 700 | `--text-primary` | Big metric in stat cards |
| Stat label | 12–13px | 500 | `--text-secondary` | Above the number |
| Body / table cell | 14px | 400 | `--text-primary` | |
| Label (form) | 13px | 500 | `--text-secondary` | Sits above inputs |
| Caption / meta | 12px | 400 | `--text-muted` | Timestamps, "by Ahmed Emad" |
| Button text | 14px | 500–600 | varies | |

Line-height ~1.4–1.5 for body, tighter (~1.2) for large headings.

---

## 3. Spacing, Radius & Elevation

**Spacing scale (4px base):** `4, 8, 12, 16, 20, 24, 32, 40`.
- Card inner padding: `16–20px`
- Gap between cards in a grid: `16–20px`
- Page content padding: `24–32px`
- Sidebar nav item vertical padding: `10px`

**Border radius:**
| Element | Radius |
|---|---|
| Buttons, inputs, dropdowns | `8px` |
| Cards, panels | `12px` |
| Icon chips / small containers | `8–10px` |
| Badges, pills, avatars | `9999px` (full) |

**Shadows (soft and low):**
- Card: `0 1px 2px rgba(16,24,40,0.04), 0 1px 3px rgba(16,24,40,0.06)`
- Dropdown / popover / elevated: `0 4px 12px rgba(16,24,40,0.10)`
- Avoid heavy or colored shadows. Borders do most of the separation work.

---

## 4. Layout Pattern

Every screen uses the same shell:

```
┌────────────┬──────────────────────────────────────────────┐
│            │  HEADER (search · notifications · help · org) │
│  SIDEBAR   ├──────────────────────────────────────────────┤
│  (~240px)  │                                              │
│            │              MAIN CONTENT                     │
│            │        (light gray canvas, cards)             │
└────────────┴──────────────────────────────────────────────┘
```

### Sidebar (~240px, fixed)
- White surface, `border-right: 1px solid --border`.
- **Top:** logo (purple rounded-square mark + "Planex" wordmark).
- **Nav items:** outline icon + label, `10px` vertical padding. Default text `--text-secondary`. Collapsible groups (e.g. "Reports" expands to sub-items).
- **Active item:** `--primary` text + icon, `--primary-soft` rounded background.
- **Bottom:** user card — circular avatar with initials, name (`--text-primary`, 14px/600), role (`--text-muted`, 12px).

### Header (~64px)
- White, `border-bottom: 1px solid --border`.
- **Left/center:** search input, full pill or rounded, magnifier icon, placeholder text muted, optional `⌘K` shortcut chip on the right of the field.
- **Right:** notification bell (with small count badge), help/question icon, and an org/office dropdown ("Abu Dhabi Office ▾").

### Content
- Background `--bg-canvas`.
- Title block (title + subtitle) on the left, primary action button(s) on the right.
- Below: stat cards / filters / the main surface (grid or table).

> ⚠️ The purple numbered squares (1, 2, 3, 4) in the reference image are **mockup annotations**, not UI. Do not reproduce them.

---

## 5. Core Components

### Buttons
- **Primary:** `--primary` fill, white text, `8px` radius, `~10px 16px` padding, 14px/600. Optional leading icon (e.g. `+`). Hover → `--primary-hover`.
- **Secondary / default:** white fill, `1px solid --border`, `--text-primary` text. Hover → `--border-strong` border / faint gray fill.
- **Tertiary / icon button:** transparent, icon only, gray; hover gives a faint gray circular/rounded background.
- Buttons sit in a horizontal row, `8px` gap, right-aligned in headers.

### Cards (template / content cards)
- White, `12px` radius, `1px solid --border`, soft card shadow, `16–20px` padding.
- Structure (top→bottom): icon chip → title (15px/600) → 2-line description (`--text-secondary`) → status badge → footer row with muted timestamp.
- Top-right of card: star/favorite outline icon + a `⋮` three-dot menu.
- Layout in a responsive grid (4 columns on wide screens).

### Stat cards
- Compact white card: small tinted square **icon chip** on the left, then label (small, muted) stacked above a large bold number.
- Used in a row of 4 (Total / Published / Drafts / Shared).

### Status badges
- Pill shape, `--fill` background + `--text` color from the status table, 12px/500, `~2px 10px` padding. Text only (no dot needed, but a leading dot is acceptable).

### Inputs & form fields
- White, `1px solid --border`, `8px` radius, `~10px 12px` padding, 14px.
- Label above in 13px/500 `--text-secondary`; required marked with `*`.
- Focus: `--primary` border + a subtle `--primary-soft` focus ring.
- Dropdowns/selects: same styling with a trailing chevron.
- Date ranges shown as two fields with a calendar icon.

### Tables (reports list)
- White surface card. Header row: 12–13px/600 `--text-secondary`, uppercase optional, on a faint background.
- Rows separated by `1px solid --border`, `~14px` vertical cell padding, hover highlights the row faintly.
- First cell often has a small format icon (e.g. red PDF glyph) + title with a muted secondary line ("by Ahmed Emad").
- Status column uses badges. Actions column uses outline icon buttons (view / download / `⋮`).
- **Pagination footer:** left "Showing 1 to 6 of 42 reports", right numbered pages (active page = `--primary` fill) + a "10 / page" selector.

### Tabs
- Horizontal, text labels, `--text-secondary` default. Active tab: `--primary` text with a `2px` `--primary` underline. Sit directly under the page/section title.

### Toggles / switches
- Pill switch; on = `--primary`, off = `--border`/gray. Used for "Required", "Show on Cover".

### Avatars
- Circular. Photo, or initials on a tinted background. Used in user card and people/distribution lists.

### Builder panels (Template Builder pattern)
- Three-column working area: **left** = palette of draggable elements (icon + label rows), **center** = document/canvas preview (A4 page on gray), **right** = contextual "Element Properties" inspector (grouped fields).
- Keep panels white, separated by `--border`, each scrollable independently.

---

## 6. Iconography
- **Style:** outline / line icons, ~1.5–2px stroke, `20px` default (`16px` inside dense rows). Lucide / Feather / Heroicons (outline) all match.
- Nav, actions, and element types all use the same line style. Avoid filled or duotone icons except small status/format glyphs (e.g. the PDF file icon).

---

## 7. Quick Do / Don't

**Do**
- Keep one accent color (indigo-violet) and let neutrals carry the layout.
- Use soft shadows + thin borders together for card separation.
- Right-align primary actions in headers; left-align titles + subtitles.
- Use pill badges with light-fill/saturated-text for any status.
- Keep generous whitespace and consistent 4px-based spacing.

**Don't**
- Don't introduce additional bright brand colors — extra hues only appear as muted status tints.
- Don't use heavy/colored drop shadows or thick borders.
- Don't mix icon styles (stay outline).
- Don't crowd cards; descriptions stay to ~2 lines with clear hierarchy.

---

## 8. Copy-paste CSS variables

```css
:root {
  /* Brand */
  --primary: #5B4FE9;
  --primary-hover: #4A3FD0;
  --primary-soft: #EFEDFE;
  --primary-text-accent: #534AB7;

  /* Neutrals */
  --bg-canvas: #F6F7F9;
  --bg-surface: #FFFFFF;
  --border: #E8EAED;
  --border-strong: #D6D9DE;
  --text-primary: #1E2430;
  --text-secondary: #6B7280;
  --text-muted: #9CA3AF;

  /* Status */
  --success-text: #1E7E4F;  --success-fill: #E4F6EC;
  --warning-text: #B45309;  --warning-fill: #FCF0DF;
  --danger-text:  #B42318;  --danger-fill:  #FDECEA;
  --info-text:    #1D6FB8;  --info-fill:    #E7F1FB;

  /* Radius */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-pill: 9999px;

  /* Elevation */
  --shadow-card: 0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06);
  --shadow-pop:  0 4px 12px rgba(16,24,40,.10);

  /* Type */
  --font: "Inter", -apple-system, "Segoe UI", Roboto, sans-serif;
}
```
