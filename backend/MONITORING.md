# Monitoring, observability and audit

This backend now ships with structured logging, request/latency metrics,
database and subsystem health checks, alerting, and a much more complete audit
trail. Everything is surfaced in **Admin → Monitoring / Alerts / Logs / Audit
logs / System**.

## What changed (read this first)

| Area | Before | Now |
|---|---|---|
| Failed logins | Unknown usernames crashed the login (a `NOT NULL` column) and were never recorded; wrong passwords were recorded without a usable reason | **Every** failure is recorded with a reason code, the human-readable reason, the typed identifier, IP and device |
| Lockout | Never worked (the counter compared a username string with a user-id column) | Works: `MAX_LOGIN_ATTEMPTS` failed passwords inside `LOCKOUT_TIME` minutes locks that account/identifier; a good login clears the count |
| Login responses | Revealed whether an account was suspended/deactivated to anyone who knew the username | Password is checked first; wrong username and wrong password return the same message and take the same time |
| Audit "user" | Only a bare user id | Username, full name, e-mail, role, status; deleted accounts keep their name (snapshot); unknown login names are shown as "No such account" |
| Audit details | JSON string stored inside a JSON column | Real JSON object, secrets redacted, old rows still readable |
| Audit coverage | A handful of explicit entries | Plus an automatic entry for **every authenticated write** (POST/PUT/PATCH/DELETE), failed logins, registrations that fail, admin changes (with before → after) |
| Logs | `setup_logging` existed but was never called | JSON files (`logs/app.log`, `error.log`, `access.log`) + live dashboard + request ids |
| Errors | Any `HTTPException` (413, 409, …) was reported as a 500 crash | Deliberate HTTP errors keep their status; real crashes are logged with a stack trace, stored, and raise a critical alert |
| Login history on user delete | Deleted with the user | Kept (user id cleared, typed identifier retained) |
| Client IP | `X-Forwarded-For` trusted from anyone | Only trusted if `TRUST_PROXY_HEADERS=true` (set it when behind nginx/a load balancer) |

## Upgrading

1. `pip install -r requirements.txt` (adds `psutil`).
2. Start the app. The schema upgrade runs automatically and is safe to repeat:
   it creates `system_events` and `alerts`, adds the new columns to
   `login_history` / `audit_logs`, makes `login_history.user_id` nullable
   (MySQL/PostgreSQL), and back-fills names for existing rows.
   An equivalent Alembic migration (`a7c1e9d4b2f0`) is included if you prefer
   `flask db upgrade`; it is idempotent, so running both is fine.
3. Optional but recommended in production: `TRUST_PROXY_HEADERS=true` (behind a
   proxy), an `ALERT_WEBHOOK_URL` and/or `ALERT_EMAILS`.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `SLOW_REQUEST_MS` | 1000 | A request slower than this is flagged and stored as an event |
| `SLOW_QUERY_MS` | 500 | A SQL statement slower than this is captured (shape only, never values) |
| `MONITOR_INTERVAL_SECONDS` | 30 | How often health checks and alert rules run |
| `MONITOR_ENABLED` | true | Turn the background evaluator off |
| `AUDIT_API_ACTIVITY` | true | Automatic audit entry for every authenticated write |
| `LOG_DIR`, `LOG_LEVEL` | `logs`, `INFO` | Where the JSON log files go / verbosity |
| `LOG_RING_SIZE`, `REQUEST_RING_SIZE` | 5000, 10000 | Size of the in-memory live buffers |
| `EVENT_RETENTION_DAYS` | 30 | Persisted events and resolved alerts older than this are purged |
| `ALERT_ERROR_RATE_WARN/CRIT` | 5 / 15 | % of 5xx in 5 minutes (needs `ALERT_MIN_REQUESTS`, default 20, requests) |
| `ALERT_P95_WARN_MS/CRIT_MS` | 1500 / 4000 | 95th-percentile response time over 5 minutes |
| `ALERT_DB_LATENCY_WARN_MS`, `ALERT_DB_POOL_WARN_PCT` | 250, 90 | Database ping / connection-pool pressure |
| `ALERT_SLOW_QUERY_BURST` | 10 | Slow queries in 5 minutes |
| `ALERT_FAILED_LOGIN_TOTAL/PER_IP/WINDOW_MIN` | 15 / 8 / 10 | Failed-login spike and brute-force detection |
| `ALERT_DISTINCT_IDENTIFIERS_PER_IP` | 5 | One IP trying this many different accounts = credential stuffing |
| `ALERT_DISK_FREE_WARN_PCT/CRIT_PCT` | 15 / 5 | Free disk space |
| `ALERT_WEBHOOK_URL` | – | Slack / Teams / Discord incoming-webhook URL |
| `ALERT_EMAILS`, `ALERT_EMAIL_MIN_SEVERITY` | –, `critical` | Comma-separated recipients (uses the existing `MAIL_*` settings) |
| `ALERT_COOLDOWN_SECONDS` | 900 | Re-notify an ongoing alert at most this often |
| `TRUST_PROXY_HEADERS` | false | Honour `X-Forwarded-For` for client IPs |

Use **Alerts → Send test alert** to confirm your webhook/e-mail work.

## Where things are

* `utils/logger.py` – JSON logging, request-id/user context, redaction
* `middleware/observability.py` – request ids, timing, access log, SQL timing, automatic audit, exception capture
* `services/telemetry.py` – in-memory request/log/latency store (per process)
* `services/monitoring_service.py` – health checks, alert rules, background evaluator
* `services/alert_service.py` – alert lifecycle (open → acknowledged → resolved) and notifications
* `services/event_service.py` – persisted system events
* `routes/monitoring.py` – `/api/admin/monitoring/*`
* `routes/admin.py` – `/api/admin/audit-logs`, `/audit-logs/export` (CSV), `/login-attempts`, `/login-attempts/summary`
* `GET /health/ready` – readiness probe (503 if the database is unreachable) for uptime monitors / load balancers

## Good to know

* Live buffers (recent requests, log lines, latency percentiles) are **per
  process and reset on restart**. If you run several workers, each has its own
  view; the persisted pieces (events, alerts, audit trail, login history, log
  files) are shared/durable. For multi-worker setups ship `logs/*.log` to a
  central collector.
* Dashboard polling (`/api/admin/monitoring/*`) is excluded from the metrics so
  watching the dashboard does not distort them.
* Passwords, tokens, private keys, ciphertext and message content are redacted
  before anything is logged or stored in the audit trail.
* An attacker can lock a *known* account by failing its password repeatedly
  (inherent to account lockouts). The lock lasts `LOCKOUT_TIME` minutes and the
  failed-login alerts make this visible.
