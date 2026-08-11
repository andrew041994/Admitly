# Render notification worker

## Current deployment boundary

This repository does not contain a Render Blueprint. The existing Admitly API is
managed in the Render dashboard, and this document deliberately does not convert
that production resource to Blueprint management. Adding a `render.yaml` without
the existing Render resource identifiers and dashboard settings could create a
second API or change the production service unexpectedly.

The repository confirms these backend settings:

- Root Directory: `backend`
- Runtime: Python 3.11.9 (`backend/.python-version` and `backend/runtime.txt`)
- Dependency file: `backend/requirements.txt`
- API application: `app.main:app`
- API health endpoint: `/health`

The repository does not record the existing API's exact dashboard build command,
start command, health-check path, production branch, auto-deploy setting, or any
pre-deploy/build migration command. Read those values from the existing API's
Render settings; do not infer or replace them while adding the worker.

## Background Worker configuration

Create a separate Render **Background Worker**, not another Web Service:

| Setting | Value |
| --- | --- |
| Name | `Admitly Notification Worker` |
| Repository | The same repository connected to the Admitly API |
| Branch | The exact production branch used by the Admitly API |
| Root Directory | `backend` |
| Runtime | Python |
| Python version | `3.11.9` (read from `.python-version`) |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python scripts/run_notification_worker.py` |
| Auto-Deploy | Match the existing API setting; enable it if backend branch changes must deploy both services |
| Health Check | None; a Background Worker has no HTTP health endpoint |
| Max Shutdown Delay | `300` seconds, so an in-progress claimed batch has Render's maximum drain window |
| Instance count | One is sufficient, but correctness does not depend on a single instance |

Do not put `alembic upgrade` in the worker build or start command. Migration
`20260805_0038` must be applied through the existing production migration process
before the worker is first started, as a separate explicitly authorized operation.

Render supervises a Background Worker independently from the API. It starts the
worker after a successful worker deploy and restarts the process after a crash or
machine restart. API restarts do not spawn worker subprocesses, worker failures do
not terminate Uvicorn, and no terminal session needs to remain open.

## Environment variables

Configure these manually in Render; never commit their production values:

| Variable | Required | Worker use |
| --- | --- | --- |
| `DATABASE_URL` | Yes | The same PostgreSQL database URL used by the API. SSL options, if required, belong in this URL; the code has no separate database SSL variable. |
| `ENV` | Recommended | Use the same environment name as the API (normally `production`); defaults to `development`. |
| `PUSH_NOTIFICATIONS_ENABLED` | Yes for live push | Set to `true` when production push delivery is authorized; defaults to `false`. |
| `PUSH_PROVIDER` | Yes for live push | Set to `expo` with live push enabled; supported values are `noop`, `mock`, and `expo`. |

The current server-side Expo integration consumes no Expo access token, project ID,
or other Expo environment variable. It posts to Expo's fixed HTTPS send and receipt
endpoints using registered device tokens. The worker does not consume `JWT_SECRET`,
AWS credentials, email-provider secrets, encryption keys, or logging variables.
Those settings exist in the shared application settings model but are not read by
the worker's notification paths. Logging is emitted to stdout/stderr at INFO level.

Prefer attaching the same Render environment group already used by the API when it
contains `DATABASE_URL`, `ENV`, and the push settings. If the API currently uses
service-local variables, either copy the required variables in the dashboard or
move them to an environment group in a separately reviewed change. Do not copy
secret values into this repository.

## Deployment checklist (not performed by this repository change)

1. Open the existing API's Render settings and record its repository, production
   branch, Auto-Deploy mode, root directory, runtime, build command, start command,
   pre-deploy command, health-check path, and attached environment groups.
2. Confirm migration `20260805_0038` has been applied through the established
   production migration workflow. Do not make the worker run migrations.
3. Add the Background Worker with the table above and attach/copy only the required
   environment variables.
4. Set `PUSH_NOTIFICATIONS_ENABLED=true` and `PUSH_PROVIDER=expo` only when live
   Expo delivery is intended and authorized.
5. Match the API's production branch. To deploy both processes on every backend
   change, both services must have Auto-Deploy enabled for that branch. If the API's
   Auto-Deploy is disabled, Render will not deploy it automatically; leave that
   existing setting unchanged until a separate decision is made.
6. Deploy the worker only after the production migration and environment changes
   have been explicitly approved. Verify logs contain
   `notification_worker_starting`, `notification_worker_startup_validated`, and
   `notification_worker_polling_started`.

The worker handles `SIGTERM` and `SIGINT` by recording the shutdown request,
finishing the current bounded polling cycle, closing its SQLAlchemy pool, and
exiting zero. Unexpected non-database failures exit non-zero immediately. Transient
database cycle failures are logged and retried; five consecutive failures terminate
non-zero so Render can restart the process. Startup configuration, connectivity,
or missing-table failures terminate non-zero without running migrations.

## Multiple-instance safety

- `notification_jobs` and `push_dispatches` claim rows with
  `FOR UPDATE SKIP LOCKED`, record `claimed_at`, and recover claims stale for ten
  minutes.
- Nearby fan-out uses a unique job key and deterministic per-user notification key.
- User notifications have a unique `dedupe_key`; push dispatches are unique per
  notification/token pair; event reminder logs are unique per event/user/type.
- Expo receipt rows stay locked while a receipt batch is polled.

These controls make normal overlapping deploy instances safe. As with any external
push provider, a hard process loss after Expo accepts a request but before its ticket
ID is committed can result in a later retry; the database cannot make that network
boundary exactly-once.
