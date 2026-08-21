# MUN Chit System

A production-oriented Django + PostgreSQL application for managing chits
(notes passed between delegates and the Executive Board) across multiple
Model UN conferences, committees, and rooms.

> **Status: All 6 phases complete.** Data model, auth and permissions,
> delegate chit submission, the full Executive Board workflow, a working
> administrator panel, a demo seed-data command, and a production-
> readiness pass are all implemented and tested against a real
> PostgreSQL database. See "12. Testing" for the full suite breakdown
> and "14. Security checklist" for what's been verified versus what
> remains a known limitation.

## 1. Project overview

MUN Chit System models the real hierarchy of a Model UN conference:

```
Conference → Committee → Room → Country Assignment → Users → Chits
```

Delegates send chits to other delegates or to the Executive Board; EB
members triage and reply; administrators configure conferences and
audit everything. Every authorization rule is enforced **server-side**,
at the database-queryset level — not just hidden in the UI.

## 2. Features (current + planned)

Implemented in Phase 1:
- Custom email-based `User` model with roles (Delegate, Executive Board,
  Committee Administrator, Super Administrator) and hashed passwords only.
- Full data model: `Conference`, `Room`, `Committee`, `CountryAssignment`,
  `CommitteeStaff`, `Chit`, `ChitReply`, `AuditLog`, `Notification`.
- Database-enforced constraints: unique committee names per conference,
  one active delegate per country per committee, one staff role per user
  per committee, self-recipient prevention.
- Role-scoped `Chit.objects.visible_to(user)` queryset — the core
  authorization layer used everywhere chits are read.
- Human-readable chit numbering (`MUN-<year>-<committee>-<sequence>`).
- Django Admin registered for every model, with audit logs made
  append-only (no add/edit, delete restricted to superusers).
- 25 passing tests, including the full cross-committee visibility
  scenario required by the spec.

Implemented in Phase 2:
- Custom email-based login (`RateLimitedLoginView`) with a cache-backed
  rate limiter: 5 failed attempts per IP+email within a 5-minute window
  locks out further attempts, including with the correct password, until
  the window expires.
- Role-based permission mixins (`DelegateRequiredMixin`,
  `ExecutiveBoardRequiredMixin`, `CommitteeAdminRequiredMixin`,
  `SuperAdminRequiredMixin`) that check *live* `CountryAssignment` /
  `CommitteeStaff` / `managed_conferences` records — never the
  denormalized `User.role` field alone — so access can never outlive a
  real assignment.
- `ActiveCommitteeMixin`: resolves the session's active committee against
  live assignment data on every request, so a stale or tampered session
  value can't grant access to a committee the user no longer belongs to.
- Multi-committee selector (`/committee/select/`): a user with more than
  one active committee assignment is shown a picker; the choice is
  stored server-side in the session and re-validated on every subsequent
  request.
- Role-scoped placeholder dashboards for Delegate, Executive Board, and
  Administrator (Committee Admin / Super Admin), wired end-to-end
  through login → role redirect → (optional selector) → dashboard.
- Audit logging on login success, login failure, and logout (never logs
  the attempted password).
- 30 additional passing tests (55 total): login success/failure, rate
  limiting (including "per-identifier, not global"), CSRF rejection,
  role-mixin access control for every role pairing, stale/mismatched
  session committee handling, and the full selector flow.

Implemented in Phase 3:
- Two-step delegate chit submission: `SendChitForm` validates server-side
  and stores a draft in the session (nothing touches the database yet);
  `PreviewChitView` renders a read-only preview, re-validates live in
  case anything changed since compose (a recipient going inactive,
  submissions being toggled off), and only then creates the `Chit`.
- Recipient list is generated from the live, active-committee-scoped
  `CountryAssignment` queryset with the sender's own assignment excluded
  at the query level — self-messaging is structurally impossible, not
  just caught after the fact (though the model's `clean()` also enforces
  it as defense in depth).
- Character counter (client-side JS) plus a real server-side max-length
  check using `min(conference.max_message_length, 2000)`.
- Delegate-to-EB messaging and submissions overall both respect their
  conference-level admin toggles (`delegate_to_eb_enabled`,
  `chit_submissions_enabled`); anonymous sending only appears in the form
  when `anonymous_chits_enabled` is on.
- Sent / Received chit history views with search (subject or chit
  number), status/category/priority filters, and pagination (15/page).
- Chit detail page scoped by `Chit.objects.visible_to(user)`, with a
  direct delegate recipient's first view auto-transitioning status
  Submitted → Delivered → Read.
- All user-generated chit content (subject, message, replies) renders
  through Django's default autoescaping — verified directly with an
  XSS-attempt payload in tests, not just assumed.
- 30 more passing tests (85 total): form validation for every rule in
  the spec (self-recipient, cross-committee, message length, missing
  confirmation checkbox, disabled toggles), the full compose→preview→
  confirm flow including a state-change-mid-flow case, sent/received
  visibility and filtering, and XSS-safe rendering on both preview and
  detail pages.

Implemented in Phase 4:
- EB inbox (`/eb/incoming/`) combining the four required queues — New,
  Unread, Urgent, Awaiting response — into one filterable view
  (`?queue=new|unread|urgent|awaiting`), plus the same search/status/
  category/priority filters used on the delegate history pages.
- Chit detail page extended with EB-only actions: **Reply** (creates a
  `ChitReply`, sets status to Replied, stamps `replied_at`) and
  **Archive** (sets status to Archived, stamps `archived_at`), gated by
  an explicit object-level permission check — `PermissionDenied` is
  raised unless the requester is genuinely EB staff *for that specific
  committee* on a chit that's actually addressed to the EB. This is
  enforced at the view layer, not just hidden in the template, and is
  covered by a test that a delegate (and an EB member of a *different*
  committee) both get rejected.
- Archive view (`/eb/archive/`) — separate from the main inbox, with the
  same filters, ordered by `archived_at`.
- The Submitted → Delivered → Read auto-transition (built for delegates
  in Phase 3) now also applies to EB recipients: any EB staff member of
  the addressed committee marks a chit Read on first view.
- 23 more passing tests (108 total): queue filtering correctness, reply
  creates the reply and updates status/timestamp, archive updates
  status/timestamp, the full object-level permission boundary (wrong
  committee, wrong role, non-EB-addressed chit), and the read-transition
  now covering EB viewers.

**A real bug found and fixed during Phase 4 (not just a test-writing
mistake):** `Chit.chit_number` has a *globally* unique database
constraint, but the number was generated as
`MUN-{year}-{committee_abbreviation}-{sequence}` — nothing in that
string is guaranteed unique across *different conferences* that happen
to reuse a common abbreviation (e.g., two separate conferences both
using "UNSC" in 2026). I hit this directly: submitting a chit in a
second test conference that also had a "UNSC" committee threw a 500
from an `IntegrityError` on save, because the generated number
collided with the first conference's `MUN-2026-UNSC-000001`. Fixed by
inserting a short, deterministic per-conference disambiguator into the
format (`MUN-{year}-{abbrev}-{conference_short_id}-{sequence}`), chosen
so the string still starts with the original `MUN-{year}-{abbrev}-`
prefix — this kept the existing 85 tests' `.startswith(...)` assertions
valid without modification, while making instance collisions the
DB-level unique constraint would need to catch a near-impossible edge
case rather than a routine occurrence. Verified live via curl: the
second conference's chit now saves successfully with a distinct number.

Implemented in Phase 5:
- Full admin panel object-level authorization: every conference/
  committee/room/delegate/staff view resolves access through the same
  `accounts.permissions.require_conference_management` helper already
  used elsewhere in the codebase (not a second, parallel permission
  check), so a Committee Administrator can only reach conferences in
  their own `managed_conferences` — verified with a live curl test that
  got a 403 on an unmanaged conference, then codified as an automated
  test.
- Conference CRUD: Super Admins create new conferences; Committee
  Admins edit/manage conferences already assigned to them. New-
  conference creation is deliberately Super-Admin-only — assigning a
  Committee Admin to a conference is a rare, high-trust action left in
  Django Admin rather than duplicated here.
- Room and Committee CRUD, nested under their conference, with
  soft-delete-style Active/Inactive toggles instead of hard deletes (so
  historical chits referencing them are never orphaned).
- Delegate and Executive Board staff assignment by email: if the email
  matches an existing account it's linked directly; if not, a new
  account is created on the spot with a randomly generated temporary
  password shown once in the success message. There's no self-service
  password reset yet, so the admin is responsible for relaying that
  password to the person directly — documented as a known limitation
  below, not hidden.
- Chit oversight list (`/admin-panel/chits/`) scoped to every conference
  the admin manages, with the same conference/committee/status/
  category/priority/search filters as the delegate and EB list views,
  and a CSV export that respects the same filters. The export
  deliberately includes subject/message content, since the requesting
  admin already has full read access to it on-screen — hiding it only
  from the export would be inconsistent, not safer.
- Per-conference chit settings page exposing every toggle already on the
  `Conference` model (submissions on/off, delegate→EB on/off, anonymous
  chits on/off, replies on/off, cross-committee on/off, max message
  length capped server-side at the hard 2000-character system limit).
- Audit log view, restricted to Super Admins only: `AuditLog` entries
  are deliberately generic (object_type/object_id, no conference FK), so
  there's no reliable way to show a Committee Admin only "their" log
  entries without fragile metadata parsing — rather than build that on
  shaky ground, full log access stays Super-Admin-only for now.
- Dashboard analytics: conference/committee/active-delegate/chit counts,
  plus a status and category breakdown, all scoped to managed
  conferences.
- 34 more passing tests (142 total): the full object-level authorization
  boundary (managed vs. unmanaged conference/committee, delegate blocked
  entirely, Super-Admin-only routes), conference/room/committee CRUD,
  delegate/staff assignment including the create-new-account and
  link-existing-account paths, duplicate-assignment rejection, settings
  toggle persistence (including the max-length upper-bound validation),
  chit list scoping and filtering, CSV export scoping, and audit log
  filtering.

Implemented in Phase 6:
- Demo seed command (`seed_demo_data`) — creates a full realistic dataset
  (one conference, three committees, three rooms, delegates, EB staff,
  an admin, and sample chits across several statuses) with a `--force`
  guardrail that refuses to run outside `DEBUG=True`, so it can't
  accidentally seed known-password accounts into a production database.
  Verified idempotent by running it twice against the same database.
- Accessibility pass with concrete fixes, not just a checklist claim:
  added `scope="col"` to every data table header across the app; added
  missing `<thead>` rows to two admin tables that had none at all (a
  genuine gap the review caught); added a visually-hidden "Actions"
  label to icon/button-only table columns; linked the chit-compose
  character counter to its textarea via `aria-describedby` rather than
  `aria-live` (a raw live region firing on every keystroke would be
  disruptive, not helpful). The skip-to-content link, semantic
  `<fieldset>`/`<legend>` grouping on the recipient-type radio group,
  and focus-visible styling were already in place from earlier phases
  and were verified rather than rebuilt.
- Production readiness: `manage.py check --deploy` runs clean (zero
  warnings) under `config.settings.prod` with realistic environment
  variables — verified the security settings it depends on
  (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
  HSTS) actually diverge from the dev defaults via `diffsettings`,
  rather than trusting a clean `check` output that might reflect an
  accidentally-permissive prod config.
- Spec-scenario coverage audit: reviewed cross-committee chit handling
  specifically, since it's the trickiest interaction in the system — a
  chit's `committee` FK always reflects the *sender's* committee, so the
  recipient's "Received chits" list has to filter by
  `recipient_country__committee`, not `committee`, or a cross-committee
  chit would silently vanish from the recipient's own inbox. Confirmed
  this was already handled correctly with a passing test
  (`test_cross_committee_chit_appears_in_recipients_received_list`)
  rather than assuming test-suite size implied coverage.
- 149 tests total, all passing against a live PostgreSQL database, with
  zero regressions introduced by the accessibility template edits
  (re-verified module by module after each change).

## 3. Technology stack

- Python 3.12, Django 6.1
- PostgreSQL 16 (via `psycopg2-binary`)
- `django-environ` for environment-based configuration
- Bootstrap 5 (planned, Phase 3+) for templates
- Django Channels (optional, scaffolded) for real-time notifications

## 4. Installation

```bash
git clone <repo-url>
cd mun_chit_system
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then edit .env with real values
```

## 5. PostgreSQL setup

```bash
sudo apt install postgresql postgresql-contrib
sudo service postgresql start

sudo -u postgres psql -c "CREATE USER mun_chit_user WITH PASSWORD 'change-me';"
sudo -u postgres psql -c "CREATE DATABASE mun_chit_db OWNER mun_chit_user;"
```

Set `DATABASE_URL` in `.env` accordingly:

```
DATABASE_URL=postgres://mun_chit_user:change-me@localhost:5432/mun_chit_db
```

## 6. Environment variables

See `.env.example` for the full list. Key variables:

| Variable | Purpose |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` or `config.settings.prod` |
| `DJANGO_SECRET_KEY` | Django secret key — must be unique per environment |
| `DEBUG` | `True`/`False` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated list of allowed hosts |
| `DATABASE_URL` | Full Postgres connection string |
| `SECURE_SSL_REDIRECT`, `EMAIL_*` | Production-only |

**Never commit `.env`.** Only `.env.example` (with placeholder values) is
tracked in version control.

## 7. Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

## 8. Demo seed command

```bash
python manage.py seed_demo_data
```

Creates one demo conference ("Global Horizons MUN 2026") with three
committees (UNSC, ECOSOC, UNHRC), three rooms, delegate/EB/admin
accounts for each, and a handful of sample chits covering different
statuses. Idempotent — safe to re-run; it reuses existing rows by
natural key rather than duplicating them. All accounts use the password
`DemoPass123!`.

Refuses to run outside `DEBUG=True` unless passed `--force`, since it
creates accounts with a publicly-known password — this is a deliberate
guardrail against accidentally seeding a production database, not an
oversight to work around.

## 9. Creating a superuser

```bash
python manage.py createsuperuser
```

Or non-interactively for local dev:

```bash
python manage.py shell -c "
from accounts.models import User
User.objects.create_superuser(email='super@example.com', password='ChangeMe123!', name='Dev Admin')
"
```

## 10. How roles and permissions work

- `User.role` is a denormalized convenience field for quick UI branching.
- The **actual source of truth** for what a user can see/do is their
  `CountryAssignment` (delegate) and `CommitteeStaff` (EB) records, plus
  `User.managed_conferences` (Committee Administrator) and
  `is_superuser` (Super Administrator).
- All chit reads go through `Chit.objects.visible_to(user)`, which
  branches by role:
  - **Delegate**: chits they sent, chits sent to their assigned country,
    or chits addressed directly to them.
  - **Executive Board**: chits addressed to the EB of a committee they
    staff.
  - **Committee Administrator**: all chits in conferences they manage.
  - **Super Administrator**: everything.
- This is enforced in the queryset layer, so it applies uniformly to
  list views, detail views, and API endpoints — a delegate cannot bypass
  it by guessing a chit's URL.

## 11. How multiple committees and rooms work

- A `Committee` belongs to exactly one `Conference` and has at most one
  `Room` assigned at a time (`Committee.room`).
- A delegate's `CountryAssignment` ties them to one committee (and
  therefore one room) at a time; that committee/room is auto-attached to
  every chit they submit and cannot be changed client-side.
- A user with assignments in multiple committees is shown a committee
  selector before the chit form loads.

## 12. Testing

```bash
python manage.py test
```

Current suite (149 tests, all passing against a live PostgreSQL test
database): custom user manager behavior, committee/country/staff
uniqueness constraints, chit numbering (including the per-conference
disambiguation fix), self-recipient prevention, the full cross-committee
visibility scenario (delegate/EB/admin/super admin, three committees,
three rooms), login success/failure, login rate limiting, CSRF
rejection, role-based permission mixins for every role pairing, the
multi-committee selector flow, delegate chit submission validation, the
compose→preview→confirm flow, sent/received history filtering and
pagination, XSS-safe rendering, EB queue filtering, reply/archive
actions, the EB object-level permission boundary, and the full admin
panel (object-level conference/committee scoping, CRUD, delegate/staff
assignment, settings, chit oversight and CSV export, and audit log
filtering).

## 13. Deployment (outline — full guide in later phase)

- Use `config.settings.prod`, with `DJANGO_SECRET_KEY`,
  `DJANGO_ALLOWED_HOSTS`, and `DATABASE_URL` set via real environment
  variables (never in source).
- Serve via Gunicorn/Daphne behind a reverse proxy terminating TLS.
- Run `python manage.py collectstatic`.
- `SECURE_SSL_REDIRECT`, HSTS, and secure cookies are already configured
  in `config/settings/prod.py`.

## 14. Security checklist (current status)

- [x] Passwords always hashed via Django's auth system, never plaintext.
- [x] PostgreSQL config entirely via environment variables.
- [x] Database-level constraints for uniqueness, not just app-level checks.
- [x] Server-side authorization via `visible_to()` queryset, not
      frontend-only checks.
- [x] Audit log model is append-only in Django Admin.
- [x] Logging filter strips anything resembling chit message/subject
      content before it reaches log output.
- [x] `.env` excluded from version control; only `.env.example` tracked.
- [x] CSRF/session/login-rate-limit middleware wired to real views
      (login rate limiting active, CSRF verified via test with
      `enforce_csrf_checks=True`, session cookies configured).
- [x] XSS-safe template rendering verified end-to-end: tested directly
      with `<script>`/`<img onerror>` payloads on the preview and detail
      pages, confirming autoescaping and no accidental `|safe` filters.
- [x] EB reply/archive actions are gated by an explicit object-level
      permission check (`PermissionDenied` if the requester isn't
      genuinely EB staff for that exact committee on a chit actually
      addressed to the EB) — not just hidden buttons in the template.
      Verified with tests for a delegate, and for an EB member of a
      different committee, both attempting the action directly via POST.
- [x] Admin panel object-level scoping shares one implementation
      (`accounts.permissions.require_conference_management`) across
      every conference/committee/room/delegate/staff view, so a
      Committee Administrator hitting a URL for a conference they don't
      manage gets a 403 regardless of which page they try — verified
      live via curl and covered by automated tests.
- [x] `manage.py check --deploy` runs clean (zero warnings) under
      `config.settings.prod` with realistic environment variables; the
      security settings it depends on (SSL redirect, secure cookies,
      HSTS) were confirmed via `diffsettings` to actually diverge from
      dev defaults rather than trusting the check output blindly. Only
      remaining step is re-verifying `ALLOWED_HOSTS` against the real
      production domain once it's known.
- [x] Data tables have proper `scope="col"` headers and no
      color-only status indicators (every badge carries a text label).
      Two admin tables that had no `<thead>` at all were caught during
      review and fixed, not just audited.

## 15. Future improvements

- Cross-conference delegate assignments.
- Individually-targeted EB messaging (vs. shared committee EB inbox).
- Full Django Channels real-time notification delivery.
- Rate limiting at the infrastructure layer (e.g. nginx) in addition to
  the application-level login throttling.
- Self-service password reset for accounts created inline by an admin
  during delegate/staff assignment — today the temporary password is
  shown once to the admin and must be relayed out of band.
- Explicit "reject" / "withdraw" chit actions (the `Status` values exist
  on the model but have no UI yet).
- Administrator recipient type in the delegate compose form (the model
  supports `RecipientType.ADMINISTRATOR`, but only Delegate and
  Executive Board recipients are exposed today).

## 16. Project structure

```
mun_chit_system/
├── manage.py
├── config/
│   ├── settings/{base,dev,prod}.py
│   ├── urls.py
├── accounts/       # custom User model, roles, auth views, permission mixins, rate limiting
├── conferences/     # Conference, Room
├── committees/       # Committee, CountryAssignment, CommitteeStaff, selectors, selector view
├── chits/            # Chit, ChitReply, role-scoped queryset, delegate/EB dashboards
├── adminpanel/         # Full admin management UI: conference/room/committee CRUD,
│                       #   delegate/staff assignment, settings, chit oversight + CSV export, audit log
├── notifications/     # Notification model, polling context processor, Channels scaffold
├── audit/              # AuditLog, append-only admin, signal-based logging (incl. auth events)
├── templates/
├── static/
├── media/
├── requirements.txt
├── .env.example
└── README.md
```

Each app maps to one piece of the domain, so permission and visibility
logic for a concept lives next to its model rather than being scattered
across views.
