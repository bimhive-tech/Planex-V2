# Planex — Product Idea & Specification (V2)

> The single source of truth for **what Planex is and does**. It is the product
> vision, distilled from the original Planex build and re-aligned to the V2 stack
> (Next.js + Django REST, PostgreSQL, Cloudflare R2, one Railway service).
> Read alongside `CLAUDE.md` (how we build) and `style.md` (how it looks).
>
> Status tags used below: **[built]** already shipped in V2 · **[next]** the
> immediate roadmap · **[later]** planned, not yet scoped in detail.

---

## 1. What Planex Is

Planex is a **multi-company SaaS platform for construction project progress
tracking and reporting**. It turns real site progress into structured,
reviewable, reportable project data.

It is not a dashboard toy and not a spreadsheet viewer. It is the **operational
layer between planning and the field**: Primavera P6 provides the schedule-oriented
structure of a project; Planex is where that structure is *used day to day* by
engineers, reviewers, project managers, company administrators, and the platform
owner.

The problem it solves: in construction, the plan lives in Primavera while the
execution reality lives in scattered site updates, spreadsheets, and chat. Planex
brings the two together in a controlled web app — define projects properly, assign
teams and scopes, collect field progress consistently, **review and approve before
it becomes official**, monitor delays, generate reports and curves, and export
accepted progress back to Primavera.

At its core Planex is not just recording numbers. It is an **accountable, traceable
system** for how progress is captured, validated, understood, and reported.

---

## 2. Product Principles

- **Modular & scalable.** Every capability is a module that can grow independently
  (auth, settings, projects, imports, progress, approvals, reports). Today it is
  progress tracking; tomorrow it is more. Build for that.
- **Large data is the default.** Assume tens/hundreds of thousands of rows per
  project. Pagination, indexing, no N+1, push aggregation to the DB. (See `CLAUDE.md` §11.)
- **Accountable by design.** Official figures come only from reviewed/approved
  data, with a permanent audit trail. Raw submissions never silently become truth.
- **In-context interaction.** Most create/edit actions happen in modals or side
  drawers, not full page switches, so users stay in their working context.
- **Tenant isolation is absolute.** A company can never see another company's data.

---

## 3. Multi-Tenancy & Company Model

Planex serves many companies from one system. Each company is an isolated
workspace: its own users, departments, roles, permissions, projects, reports,
and exports. **No data crosses company boundaries.**

There is one special **administrative ("platform") company**, used only by the
system owner. It exists to create companies, create each company's first admin,
and manage the platform at the top level. The first seeded account lives here.

- Seeded platform company: **Admin** (`is_platform_admin = true`). **[built]**
- Seeded super admin: **superadmin@planex.app** / `12345678` (env-overridable). **[built]**

Within each company, Planex supports a real internal structure: users, departments,
roles, and permissions, with users assignable to **one or more roles** and **one or
more departments** (people often wear several hats on site).

**V2 status:** the company/identity layer is built — see the **Settings** module
(§16). Companies are created shell-first by the platform admin; each new company is
seeded with default roles. **[built]**

---

## 4. Identity, Roles, Permissions & Scope

Access control works on **two dimensions**:

### 4.1 Action permissions — *what* a user may do
Controlled through **roles**. A role holds a set of permission keys. Examples:
manage company, manage users, manage roles, manage projects, view projects, submit
progress, review progress, approve progress, export reports, (+ platform-only:
manage companies, manage platform).

- Permission keys are defined **once** in the backend and mirrored on the frontend. **[built]**
- A user's effective permissions = the union across their active roles; platform-company
  users implicitly hold everything. **[built]**

### 4.2 Scope permissions — *where* a user may act
Defines the slice of the organization/project a user may work in. A site engineer
may submit progress, but **only** for specific projects, zones, buildings, or areas
assigned to them. A reviewer approves only within their responsibility. This makes
Planex **role-based *and* scope-aware**. **[next — project scope assignments]**

### 4.3 Default & locked roles (per company)
Every company is seeded with: **[built]**
- **Company Admin** — all company (non-platform) permissions; **locked** (cannot be
  edited or deleted).
- **User** — minimal permissions; editable but **not deletable**.
- Custom roles are fully editable and deletable (unless assigned to users).

### 4.4 Managing roles & permissions
- **Roles** tab: create / rename / delete custom roles. **[built]**
- **Permissions** tab: a matrix — permissions as rows, roles as columns — toggle a
  checkbox to grant/revoke; locked roles are read-only. **[built]**

---

## 5. The Project Model

A project is a structured tracking environment with both a **descriptive identity**
and an **operational structure**.

**Descriptive side** (set at creation, editable later):
- name, project type (Commercial / Residential / Infrastructure / Industrial),
  location, total area (sqm), description/notes
- client (company-scoped client record, reusable), client name
- consultant (name, phone, email), contractor (name, phone, email)
- planned start / planned finish / revised finish
- optional workflow template, optional report/export template

**Operational side:** the work-tracking hierarchy (§6) plus assigned team and scopes.

Projects are **company-scoped**, can be archived, and are listed in the **Project
Hub**. Create/edit happens in a side drawer (in-context). **[next]**

---

## 6. Work Structure & Hierarchy

Planex tracks work through a standard but **flexible** construction hierarchy:

```text
Phase → Zone → Building → Area / Room → BOQ Item / Activity
```

This reflects how projects are physically organized, but **not every project uses
every layer** — some have no building level, some don't track rooms. The hierarchy
stays structured yet optional so it can mirror the real shape of a project.

- A flexible self-referencing **scope** tree models phase/zone/building/area levels;
  zones and subzones carry **area (sqm)** and a **weight**.
- Progress is **always** entered at the BOQ item / activity (leaf) level and anchored
  to its full project path. There are no disconnected progress values.

### 6.1 BOQ item / activity progress type
Each activity is defined **at setup/import time** as one of:
- **Percentage-based** — engineer records a completion %.
- **Quantity-based** — engineer records executed quantity vs a planned/target quantity.

This is a system rule, not a per-entry choice, so field entry stays consistent. The
item type drives the entry form and the roll-up math. **[next]**

---

## 7. Workflow Templates

Companies define **reusable project structures** so projects don't start from
scratch. **[later]**

- **Workflow template**: a named, weighted set of **phases**.
- **Task library**: company-scoped reusable tasks with default weights.
- A phase contains weighted **phase-tasks** drawn from the library.
- When applied to a project, the template is **snapshotted** onto the project
  (workflow/phase/task snapshots) so later edits to the template don't rewrite
  historical project structure.

A **Workflow Builder** UI manages template info, phases, and task assignments
together (in-context, not separate pages).

---

## 8. Primavera Relationship & File Flow

Planex does **not** replace Primavera as the planning system. P6 remains the source
of the schedule; Planex turns that structure into field-execution tracking. **[later]**

Flow:
1. Planner maintains the schedule in **Primavera P6**.
2. Planner exports the relevant schedule as an **Excel** file (the standard
   `FOR (P6)` template is the preferred path).
3. File is **uploaded** into Planex.
4. Planex **parses** it and establishes/updates the project hierarchy, activities,
   and tracking context. When the file matches the expected template it's processed
   directly; when it differs, a **column-mapping** flow lets the user map columns to
   the fields Planex needs.
5. After progress is recorded and **accepted**, Planex can **export** accepted
   progress back in a **Primavera-compatible** format (round-trip), replaying the
   captured P6 column structure/formulas via stored `schedule_template_metadata`.

Import is a **long-running job** with real lifecycle: live status milestones
(zones/subzones/phases/tasks found, then clearing/creating/writing checkpoints),
a **cancel** action, worker-PID health checks, and stale-import recovery. Parsing
happens outside the long DB write so status stays live.

---

## 9. Progress Entry Workflow (Fieldwork)

The most important daily flow. A site engineer opens a project, navigates to the
correct place in the hierarchy (phase → zone → building? → area/room? → activity),
and the system shows the **correct input form** based on the activity type
(% or quantity). The engineer can add notes, remarks, and delay comments. **[next]**

On submission Planex records: the submitted value, submitter identity, timestamp,
attached remarks/delay notes, and the full project path. Editing happens in a
**side drawer** scoped to the user's assignment; optional **file/image attachments**
(stored in Cloudflare R2 via short-lived presigned URLs) can be added per progress
row, with upload/delete history kept.

At submission the entry is **pending** — it does not yet change official figures.

---

## 10. Approval Chain & State Logic

Submitted progress is **not** automatically official. Planex separates raw
submissions from accepted data with a sequential chain: **[next]**

1. **Engineer submits** → entry is *Pending Review*.
2. **Reviewer reviews** → approves, or rejects with a required comment.
3. **Project Manager approves** → final acceptance, or rejects back with a comment.

Submission states: **Pending Review · Reviewer Rejected · Pending PM Approval ·
PM Rejected · Accepted**. Only **Accepted** values affect roll-ups, reporting,
exports, and dashboards.

A rejected submission is **never deleted** — it stays in history with its rejection
reason. Correcting it creates a **new** submission that re-enters the chain from the
start; the rejected entry remains in the permanent audit trail.

---

## 11. Progress Roll-Up & Calculation

Once a submission is accepted, Planex **recalculates progress upward** through the
hierarchy automatically — the user never aggregates by hand. **[next]**

- An accepted leaf update rolls up: activity → area/room → building → zone → phase →
  project summary.
- Default roll-up is **weighted by planned quantity** (large-quantity items
  contribute more than small ones — no meaningless averages).
- At project level the weighting basis is **configurable to cost weight** where teams
  want cost-significance instead of quantity-significance. This is a project rule,
  not a per-use toggle.
- For each level Planex tracks both **planned progress** (from the imported schedule,
  at a date) and **actual accepted progress** (from approved submissions). Their
  difference drives variance, delay analysis, and the **SPI** (schedule performance
  index) shown in reports.

---

## 12. Delays & Issues

Delays are first-class, not an afterthought. **[later]**

- A submission behind planned progress can carry a **delay reason / issue note**.
- Each project has a dedicated **Delays / Issues** space to view, filter, and analyze
  delays, tied to real context (phase/zone/building/area/activity) with cause notes,
  dates, status, and remarks — producing not just a list but analysis of *what* is
  causing slippage and *where*.

---

## 13. Notifications & Audit Trail

Because Planex is workflow-driven, state transitions notify the relevant people:
submit → reviewer notified; reviewer-approve → PM notified; reject → engineer
notified with reason; accept → relevant users see it became official. **[later]**

Every submission carries a **full audit trail**: who submitted what and when, who
reviewed, every decision at each stage, when, the comments left, and the final
accepted value. A dedicated progress-audit record captures old/new progress, planned
progress, status, and notes on each change. The trail is permanent. **[next — audit]**

---

## 14. Dashboards & Reports

Reporting is a core feature — the point of collecting progress is to turn it into
**visibility** people can act on.

### 14.1 Main dashboard **[later — redesign]**
The operating view after sign-in, tailored to the user's role and scope: project
health signals, pending approvals, recently updated projects, recent submissions,
significant planned-vs-actual gaps. (V2 currently ships a placeholder dashboard,
slated for redesign once the metric data exists.)

### 14.2 Project overview **[next]**
Per-project summary: overall planned vs actual, progress at major levels (zones/
buildings), recent updates, and clear behind-plan indicators. Two modes: a
structured **Details** view and an optional movable-card **Canvas**.

### 14.3 Visual reporting **[later]**
- **S-curve** — planned vs actual cumulative progress over time.
- **Planned-vs-actual** and **comparison** charts across zones/buildings/scopes.
- **Delay/issue** reporting grouped to surface repeated causes and affected areas.

### 14.4 Monthly PDF report **[later]**
A shareable, client-ready export built **only from live data** (no faked values):
cover (company logo, project/client/consultant/contractor details), actual/planned/
**SPI** summary cards, planned-vs-actual chart, progress curve, zone chart, phase
chart, zone & phase summary tables, task progress snapshot, delays/issues table,
progress notes. Arabic text shaping is supported for imported names.

### 14.5 Report/template builder **[later]**
A **Template Builder** with a live A4 preview and controls for margins, header/footer
guides, logo placement, secondary logo, page border, table styling, and rows-per-page.
Templates can be created/activated/duplicated/reset per company.

### 14.6 Primavera-compatible export **[later]**
Export accepted progress back to the P6 Excel structure (see §8).

---

## 15. Object Storage (Cloudflare R2)

All user files — report PDFs, progress attachments, images — live in **Cloudflare
R2** (S3-compatible), in **private** buckets. Files are served via **short-lived
presigned URLs** (sensitive business data, never a public URL). Validate type/size
on upload; store object keys (not full URLs) on the model. Config via env only. **[next]**

---

## 16. Page / Navigation Structure

### Global pages
| Page | Purpose | Status |
|---|---|---|
| Sign In | Email + password auth (no public sign-up; users are created internally). | **[built]** |
| Dashboard | Role-relevant operating view; health, pending work, recent updates. | placeholder **[built]**, redesign **[later]** |
| Project Hub | List / create / edit / open / archive / delete projects. | **[built]** |
| Settings | Company-level admin (tabs below). | **[built]** |
| Workflow Templates | Reusable project structures & task library (Builder). | **[later]** |
| Account Settings | Personal settings, password, own permissions. | **[later]** |

**Settings tabs (built):** **Info** (own company profile) · **Users**
(list/search/filter-by-role, create/edit incl. email+password, delete) · **Companies**
(platform admin: create shell + delete with typed confirm) · **Roles** (create/rename/
delete) · **Permissions** (role × permission matrix). Platform admin can act across
companies via a company selector; others are locked to their own company.

### Project detail tabs **[next / later]**
| Tab | Purpose |
|---|---|
| Overview | Description, dates, stakeholders, summary progress, charts, delay visibility. |
| Schedule | Grid view of the imported hierarchy with planned/accepted progress. |
| Fieldwork | Engineers enter/update progress within their assigned scope. |
| Approvals | Reviewer/PM queue to approve or reject pending submissions. |
| Delays / Issues | Delay records, causes, affected scopes, remarks. |
| Reports & Exports | Visual reports, monthly PDF, Primavera-compatible export. |
| Team & Access | Project team assignments, scope configuration, visibility. |

---

## 17. Interaction Style

Planex should not force page-switching for small actions. Creating/editing projects,
users, assignments, uploading Primavera files, entering progress, approving/rejecting,
and logging delays all happen through **modals or side drawers** so users stay in
context. Full-page navigation is reserved for moving between major sections. Modals
dismiss only via their explicit close/cancel (not accidental outside-clicks).

---

## 18. Roadmap (build phases)

1. **Auth & tenancy** — email login, JWT httpOnly cookies, platform seed. **[built]**
2. **Settings** — companies, users, roles, permissions matrix, default/locked roles. **[built]**
3. **Dashboard redesign** — once real metrics exist. **[later]**
4. **Projects module** — Project Hub + create/edit drawer + project detail shell. **[built]**
5. **Hierarchy** — Phase→Zone→Building→Area→Activity tree + Schedule tab + weighted
   roll-up + progress donut. **[built]** · per-user scope assignments **[next]**
6. **Fieldwork** — scoped progress entry (% / quantity), attachments (R2). **[next]**
7. **Approvals** — reviewer → PM chain, statuses, resubmission, audit trail. **[next]**
8. **Roll-up & overview** — weighted aggregation, planned vs actual, SPI. **[next]**
9. **Delays & issues**, **notifications**. **[later]**
10. **Primavera import/export**, **reports & PDF**, **template builder**. **[later]**

---

## 19. Glossary

- **Platform / Admin company** — the single `is_platform_admin` company that owns the
  system and creates other companies.
- **Scope** — a node in the project hierarchy (phase/zone/building/area).
- **Activity / BOQ item** — the leaf where progress is entered (% or quantity).
- **Snapshot** — a frozen copy of a workflow/phase/task on a project, so template
  edits don't rewrite project history.
- **Accepted** — a submission that passed the full approval chain and counts toward
  official figures, roll-ups, and exports.
- **SPI** — Schedule Performance Index; actual vs planned progress.
- **Roll-up** — automatic upward aggregation of accepted progress through the hierarchy.

---

## 20. V2 deviations from the original Planex

- **Stack:** Next.js (App Router) + DRF API + PostgreSQL, deployed as **one Railway
  service** (Next front door proxies `/api` to internal Django). The original was a
  Django-templates monolith.
- **Storage:** **Cloudflare R2** (the original used Supabase storage).
- **Look:** light, indigo-on-neutral design per `style.md` (the original explored a
  dark theme). Calm, content-first, one accent color.
- **Auth:** email + password, **JWT in httpOnly cookies**, silent refresh.
- Planex V2 is a clean rebuild — the original is **reference only**; we carry over the
  ideas, not the code.
