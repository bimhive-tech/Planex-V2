# Planex V2

Multi-company SaaS for construction project progress tracking & reporting.
A clean rebuild of Planex — same domain, new stack, no legacy baggage.

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js (App Router) + React + TypeScript, pure CSS Modules |
| Backend | Django + Django REST Framework (API-only) |
| Database | PostgreSQL (Railway) |
| Object storage | Cloudflare R2 (S3-compatible) — wired, creds pending |
| Hosting | Railway — **single service** (Next + Django in one container) |

See `CLAUDE.md` (engineering rules) and `style.md` (design system).

## Architecture: one Railway service, two processes

Next.js is the public front door on Railway's `$PORT`. Django (gunicorn) runs
internally on `:8000`. Next **rewrites** proxy `/api/*`, `/admin/*`, `/static/*`,
and `/healthz` to Django. Server Components call Django directly via
`BACKEND_INTERNAL_URL`. Auth is JWT stored in **httpOnly cookies**.

```
Browser ──> Next.js (:$PORT) ──┬─ /api, /admin, /static, /healthz ─> Django (gunicorn :8000)
                               └─ everything else ───────────────> Next (SSR / Server Components)
```

> Trailing slashes: Django requires them; Next's `:path*` matcher drops them.
> So `next.config.mjs` uses `skipTrailingSlashRedirect` + appends the slash in
> the proxy destinations (`/api/:path*/`). Don't "simplify" this away.

## Local development

Two terminals (frontend proxies `/api` to the backend):

```bash
# 1) Backend  (http://127.0.0.1:8000)
cd backend
python -m venv .venv
.venv/Scripts/activate           # Windows;  source .venv/bin/activate on *nix
pip install -r requirements.txt
# backend/.env already points at the Railway Postgres public proxy
python manage.py migrate
python manage.py seed_platform   # creates Admin company + SuperAdmin
python manage.py runserver 127.0.0.1:8000

# 2) Frontend (http://localhost:3000)
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 → redirected to `/login`.
Sign in: **superadmin@planex.app** / **12345678**.

Backend tests: `cd backend && python manage.py test`.

## Deploy (Railway)

One service, built from the root `Dockerfile` (`railway.json` selects it).
Set the env vars from `.env.example` in the Railway service (Railway injects
`DATABASE_URL` automatically). `start.sh` runs migrations, seeds the platform
admin (idempotent), starts gunicorn, then Next on `$PORT`. Health check: `/healthz`.

## Project layout

```
backend/   Django project (config/) + apps/accounts (multi-tenant auth)
frontend/  Next.js app (src/app routes, components/{ui,layout}, lib, hooks, styles)
Dockerfile start.sh railway.json   single-service deploy
```

## Status

- [x] Multi-tenant auth: Company / User / Role / Department / Membership (UUID PKs)
- [x] Email + password login, JWT httpOnly cookies, login/logout/refresh/me
- [x] Platform seed (Admin company + SuperAdmin), permission model
- [x] App shell (responsive sidebar/header), protected routes, dashboard
- [ ] Companies module (platform admin creates companies + company admins)
- [ ] User management (company admin creates users)
- [ ] Projects, hierarchy, progress entry, approvals, reports (later modules)
