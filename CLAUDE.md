# CLAUDE.md — Engineering Rules & Conventions

> Read this **together with `style.md`**.
> `style.md` = how the product **looks** (tokens, components, colors).
> `CLAUDE.md` = how the product is **built** (architecture, code style, structure).
> If the two ever conflict, ask before guessing.

---

## 0. Stack (fixed — do not substitute)

| Layer | Tech | Notes |
|---|---|---|
| Frontend | **Next.js (App Router) + React + TypeScript** | TypeScript required — it lets the AI generate correct code with fewer round-trips |
| Styling | **Pure CSS via CSS Modules + CSS custom properties** | ❌ No Tailwind, ❌ no Bootstrap, ❌ no CSS-in-JS libraries |
| Backend | **Django + Django REST Framework** | API-only backend (JSON) |
| Database | **PostgreSQL** | Accessed only through the Django ORM + migrations |
| Object storage | **Cloudflare R2** (S3-compatible) | For report PDFs, attachments, images |
| Hosting | **Railway** | Frontend, backend, and Postgres deployed as Railway services |

> ⚠️ **This app handles large data volumes.** Performance is a first-class requirement, not a nice-to-have. Every list endpoint, every table, and every query must assume tens/hundreds of thousands of rows. See §11–§13.

---

## 1. Golden Rules (non-negotiable)

1. **No inline styles.** Never `style={{ color: '#fff' }}`. The only exception is passing a **dynamic CSS variable**, e.g. `style={{ ['--progress']: `${pct}%` }}`, which the stylesheet then consumes.
2. **Everything is a reusable component.** If a piece of UI appears (or could appear) twice, it's a component. No copy-pasted markup or styles.
3. **No hardcoded values.** No magic numbers, no literal API URLs, no bucket names, no secrets, no placeholder/lorem/`TODO` left in delivered code. Values come from **design tokens** (CSS vars from `style.md`), **constants**, or **environment variables**.
4. **Keep files small.** Split large files. One component per file. If a file passes ~200 lines, extract sub-components, hooks, or helpers.
5. **Comment the *why*, not the *what*.** Code should be self-explanatory; comments explain intent, edge cases, and non-obvious decisions. Be terse — low token cost, high signal.
6. **Mobile, tablet, and desktop must all work.** Every screen and component is responsive and is verified at all three widths. Mobile is the priority.
7. **Reuse before you write.** Check `components/ui` and `lib/` first. Extend an existing primitive instead of creating a near-duplicate.

---

## 2. Repository Structure

```
repo/
├─ frontend/          # Next.js app
├─ backend/           # Django project
├─ style.md
├─ CLAUDE.md
└─ .env.example       # all required keys, NO values committed
```

### Frontend
```
frontend/src/
├─ app/                       # routes only (App Router)
│  ├─ (dashboard)/
│  │  ├─ reports/page.tsx
│  │  └─ layout.tsx           # AppShell wrapper
│  ├─ layout.tsx              # root layout, imports global CSS once
│  └─ page.tsx
├─ components/
│  ├─ ui/                     # generic primitives (match style.md)
│  │  └─ Button/
│  │     ├─ Button.tsx
│  │     ├─ Button.module.css
│  │     └─ index.ts          # barrel export
│  ├─ layout/                 # AppShell, Sidebar, Header, Container, Stack, Grid
│  └─ features/               # composite, domain-specific (ReportTable, TemplateCard…)
├─ hooks/                     # reusable React hooks (useMediaQuery, useReports…)
├─ lib/
│  ├─ api.ts                  # single API client (reads base URL from env)
│  ├─ constants.ts            # non-design constants (route paths, page sizes…)
│  └─ utils.ts
├─ styles/
│  ├─ tokens.css              # :root design tokens — copied from style.md §8
│  ├─ reset.css               # minimal CSS reset
│  ├─ globals.css             # base element styles; imports tokens.css + reset.css
│  └─ breakpoints.ts          # breakpoint px constants for JS use
└─ types/                     # shared TypeScript types
```

### Backend
```
backend/
├─ config/
│  ├─ settings/
│  │  ├─ base.py              # shared settings, all secrets via env
│  │  ├─ dev.py
│  │  └─ prod.py
│  ├─ urls.py
│  └─ asgi.py / wsgi.py
├─ apps/
│  ├─ users/
│  ├─ reports/
│  │  ├─ models.py
│  │  ├─ serializers.py
│  │  ├─ views.py             # thin: validation + delegate
│  │  ├─ services.py          # business logic lives here
│  │  ├─ urls.py
│  │  └─ tests.py
│  └─ templates_app/
├─ manage.py
└─ pyproject.toml / requirements.txt
```

---

## 3. Frontend Rules (Next.js + React)

### Components
- **One component per file.** Folder per UI primitive with a barrel `index.ts` so imports stay clean: `import { Button } from '@/components/ui/Button'`.
- **Typed props.** Every component has a TypeScript `Props` interface. Provide sensible defaults; never require a prop just to fill a placeholder.
- **Composition over configuration.** Prefer `children` and small focused props over giant prop objects with dozens of flags.
- **Presentational vs. data.** `components/ui` and `components/layout` are presentational (no data fetching). Data fetching lives in Server Components, route files, or hooks, and is passed down as props.
- **Server Components by default;** add `'use client'` only when you need state, effects, or browser APIs.

### Styling (pure CSS)
- **CSS Modules only:** every component has a colocated `Component.module.css`. Class names are scoped automatically — no BEM prefixes needed.
- **Tokens are the single source of truth.** Use `var(--primary)`, `var(--radius-md)`, etc. from `tokens.css`. **Never** write a raw hex, raw box-shadow, or themed pixel value in a component module.
- **Share styles with `composes`**, not duplication:
  ```css
  /* Card.module.css */
  .card { composes: surface from '../../styles/shared.module.css'; padding: 20px; }
  ```
- **`globals.css` is imported exactly once** (in the root `app/layout.tsx`). Component modules are never imported globally.
- Keep selectors flat (one level). No deep descendant chains, no `!important`.

### Responsive (mobile-first — REQUIRED on everything)
- **Write base styles for mobile first**, then layer up with `min-width` media queries.
- **Breakpoints (use these exact values):**

  | Name | Range | Media query |
  |---|---|---|
  | Mobile | `0 – 767px` | (base styles, no query) |
  | Tablet | `768 – 1023px` | `@media (min-width: 768px)` |
  | Desktop | `≥ 1024px` | `@media (min-width: 1024px)` |

- ⚠️ **CSS custom properties cannot be used inside `@media` conditions.** Write the px literally in the query, and mirror the same numbers in `styles/breakpoints.ts` for any JS/`useMediaQuery` logic. Keep them in sync.
- Prefer fluid techniques over fixed widths: `%`, `rem`, `clamp()`, `min()`/`max()`, and CSS Grid `repeat(auto-fit, minmax(...))`.
- **Layout behavior across sizes (matches `style.md`):**
  - **Sidebar:** full-width fixed rail on desktop → collapsed/icon rail on tablet → off-canvas drawer behind a hamburger on mobile.
  - **Card grids:** 4 cols (desktop) → 2 (tablet) → 1 (mobile).
  - **Data tables:** full table (desktop/tablet) → stacked card rows on mobile (label/value pairs), never a horizontally-scrolling wall of tiny text.
- Provide a `useMediaQuery` hook in `hooks/` for any JS that needs to branch on breakpoint — don't read `window.innerWidth` ad hoc.

### Data & state
- One API client in `lib/api.ts`; base URL from `process.env.NEXT_PUBLIC_API_URL`. No `fetch('http://localhost...')` scattered around.
- Local UI state with `useState`/`useReducer`. Don't add a global state library unless a real cross-tree need appears.

---

## 4. Backend Rules (Django + DRF)

- **Thin views, fat services.** Views validate input and return responses; all business logic lives in `services.py`. Keeps views readable and logic testable.
- **One serializer per use case.** Don't overload a single serializer with conditional fields.
- **Models:**
  - **Users use a UUID primary key** (`id = UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`). UUIDs avoid exposing sequential counts, prevent ID-enumeration attacks, and are safe to use in URLs and R2 object keys. Apply the same to any other resource exposed in a public URL (reports, attachments).
  - Explicit field types; use `DecimalField` for money/quantities (never `FloatField`), `DateField`/`DateTimeField` for dates.
  - Use `TextChoices` for enums (e.g. report status: Draft / Submitted / Approved). Status strings are defined **once** here and reused — never re-typed as literals elsewhere.
  - Add DB-level constraints and `indexes` for fields you filter/sort on (status, project FK, dates).
- **Migrations are committed** and reviewed. Never edit the DB outside migrations.
- **REST conventions:** plural resource URLs (`/api/reports/`), proper status codes, pagination on list endpoints (page size from settings, not hardcoded per-view).
- **Auth & permissions** declared explicitly on every view — no endpoint ships open by accident.

---

## 5. PostgreSQL Rules
- Access **only** through the ORM + migrations. No raw SQL unless there's a measured performance need, and then it's commented with the reason.
- Index foreign keys and frequently filtered columns.
- Enforce integrity at the DB layer (`unique`, `null=False`, check constraints) — not just in serializers.

---

## 6. Cloudflare R2 (object storage)
- R2 is **S3-compatible** → use `django-storages` + `boto3` (`S3Boto3Storage`) with R2's `endpoint_url`.
- **All R2 config comes from env vars** — nothing hardcoded:
  `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_ENDPOINT_URL`.
- Buckets are **private**. Serve files (report PDFs, attachments) via **presigned URLs** with short expiry — reports are sensitive business data. Never build/expose a public bucket URL string.
- Validate file type and size on upload; store keys (not full URLs) on the model.

---

## 7. Configuration & Secrets (no hardcoding, ever)
- Every secret, URL, key, bucket, and tunable lives in environment variables.
- Commit a **`.env.example`** listing every required key with empty/placeholder-only values; never commit real `.env`.
- Frontend env vars exposed to the browser **must** be prefixed `NEXT_PUBLIC_`. Anything sensitive stays server-side.
- Django reads env via `os.environ` / `django-environ`. `DEBUG=False` in prod; `SECRET_KEY`, DB creds, and R2 creds all from env.

---

## 8. Code Style & Comments (token-efficient)
- **Top-of-file comment:** one line stating the file's purpose.
- **Docstrings/JSDoc** on exported components, hooks, services, and serializers — short: what it does, key params, gotchas.
- **Explain intent, not syntax.** `// presign 15-min URL so the link can't be shared long-term` ✅. `// loop over array` ❌.
- Delete dead code, commented-out blocks, and stray `console.log` / `print` before finishing.
- Prefer descriptive names over comments. Small, single-purpose functions.

---

## 9. Naming Conventions
| Thing | Convention | Example |
|---|---|---|
| React components / files | PascalCase | `ReportTable.tsx` |
| Hooks | camelCase, `use` prefix | `useMediaQuery.ts` |
| CSS module classes | camelCase | `.cardHeader` |
| Constants | UPPER_SNAKE_CASE | `DEFAULT_PAGE_SIZE` |
| Python modules / functions | snake_case | `report_service.py` |
| Django models | PascalCase singular | `Report`, `Template` |
| API routes | kebab/plural | `/api/project-reports/` |
| Env vars | UPPER_SNAKE_CASE | `NEXT_PUBLIC_API_URL` |

---

## 11. Performance & Scale (large data — REQUIRED)

This app will hold a lot of rows. Assume every list is huge. Slow or unbounded queries are bugs.

### Backend / database
- **Pagination is mandatory on every list endpoint.** Never return an unbounded queryset. Use **cursor pagination** (DRF `CursorPagination`) for large/append-heavy tables (reports, activity) — it stays fast at any offset; offset pagination degrades on deep pages.
- **Kill N+1 queries.** Always use `select_related` (FKs) and `prefetch_related` (M2M / reverse FKs) on querysets that serialize related objects. A table of reports showing project + author must not fire one query per row.
- **Fetch only what you need:** `.only(...)` / `.defer(...)` / `.values(...)` for list views; don't hydrate full models to render a table.
- **Index everything you filter, sort, or join on** (status, project FK, dates, owner). Add composite indexes for common filter combinations (e.g. `(project, status, -created_at)`).
- **Push work to the DB:** aggregate with `annotate`/`aggregate`, filter in the query — never load rows into Python to count or sum them.
- **Cache hot, expensive, rarely-changing reads** (dashboard stat counts, etc.). Use a cache layer (Railway Redis or Django cache) with sensible TTLs; invalidate on write.
- Enable **persistent DB connections** (`CONN_MAX_AGE`) so each request doesn't pay connection setup cost.
- Do heavy/slow work (PDF generation, bulk exports, emails) **off the request cycle** in a background worker (e.g. a separate Railway worker service) — return fast, process async.

### Frontend
- **Never fetch a whole table.** Drive lists from the paginated API; use **infinite scroll or pagination**, and **virtualize** very long lists/tables (render only visible rows).
- **Debounce search/filter inputs** (~300ms) so typing doesn't spam the API.
- Lean on **Server Components + streaming** for initial data; keep client bundles small via **code-splitting / dynamic import** of heavy components.
- Use **`next/image`** for all images (R2-served included) — automatic resizing, lazy-loading, modern formats.
- Cache and dedupe requests; show data progressively instead of blocking the whole screen.
- Memoize expensive renders (`useMemo`/`React.memo`) only where measured — don't pre-optimize blindly.

---

## 12. Error Handling & Resilience (REQUIRED)

Nothing ships that can crash on a failed request or an empty list.

### Frontend
- **Every data-driven view handles four states:** `loading`, `error`, `empty`, and `success`. No screen assumes data exists.
- Wrap route segments in **React Error Boundaries** (`error.tsx` in App Router) so one failed component doesn't white-screen the app.
- The `lib/api.ts` client centralizes error handling: it parses non-2xx responses into typed errors, and callers surface them as inline messages or toasts — never a raw thrown object in the UI.
- Show **user-readable messages** ("Couldn't load reports — retry"), never raw stack traces or status codes.
- Skeleton loaders (matching `style.md` cards/tables) over spinners where possible — perceived speed matters at scale.

### Backend
- Use a **DRF custom exception handler** so all API errors return a consistent JSON shape (`{ "error": { "code", "message", "details" } }`) with correct HTTP status codes.
- **Validate input in serializers**; return `400` with field errors, never a `500`.
- **Log errors** with context (structured logging) — Railway captures stdout/stderr, so log there. **Never leak stack traces or secrets** to clients in production (`DEBUG=False`).
- Make writes **idempotent / transactional** where it matters (`transaction.atomic`) so a partial failure doesn't corrupt data.

---

## 13. Deployment (Railway)

- **Three services minimum:** frontend (Next.js), backend (Django), and **Railway Postgres**. Add **Redis** (cache/queue) and a **worker** service if/when background jobs are introduced.
- **Bind to Railway's `PORT` env var** — never hardcode a port. Backend runs under **Gunicorn** (or Uvicorn for ASGI): e.g. `gunicorn config.wsgi --bind 0.0.0.0:$PORT`.
- **All config via Railway environment variables** — same keys as `.env.example`. Railway injects the Postgres connection as `DATABASE_URL`; parse it with `dj-database-url`/`django-environ`. R2 creds, `SECRET_KEY`, `ALLOWED_HOSTS`, and the frontend's `NEXT_PUBLIC_API_URL` are all set in Railway, never in code.
- **Run migrations on deploy** (release/start command: `python manage.py migrate --noinput`), then start the server. Never migrate manually against prod by hand.
- **Static files:** collect with WhiteNoise (`collectstatic`) for Django admin/DRF; all user media goes to **R2, not Railway disk** (Railway filesystems are ephemeral — uploaded files would vanish on redeploy).
- **Health check endpoint** (e.g. `/healthz`) for Railway to probe.
- `ALLOWED_HOSTS` and **CORS** restricted to the real frontend domain — no wildcards in prod.

---

- [ ] No inline styles; all colors/spacing/radius come from `style.md` tokens.
- [ ] No hardcoded URLs, keys, bucket names, or placeholder/`TODO` content.
- [ ] New UI is a reusable component; no duplicated markup or CSS (`composes` used where shared).
- [ ] Works and looks correct at **mobile, tablet, and desktop** widths.
- [ ] Files are small and focused; nothing over ~200 lines without a reason.
- [ ] Exported code is documented with short, intent-focused comments.
- [ ] Backend logic is in services; migrations created; permissions set.
- [ ] Secrets/config read from env; `.env.example` updated if new keys were added.
- [ ] List endpoints are **paginated** and free of N+1 queries (`select_related`/`prefetch_related`); filtered/sorted columns are **indexed**.
- [ ] Every data view handles **loading, error, empty, and success** states; errors are caught and shown readably.
- [ ] Users (and public-URL resources) use **UUID** primary keys.
- [ ] No hardcoded ports/hosts; binds to `$PORT`; deploy runs migrations; user files go to R2, not Railway disk.
