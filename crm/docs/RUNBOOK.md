# Runbook: KGL Customer Growth System

## Environment variables (Render dashboard; never commit)
| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Supabase **session pooler** string (port 5432, user `postgres.<ref>`). Not the direct address (IPv6 only) and not port 6543 |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | **First start only:** creates the first administrator when there are no accounts yet. After that, accounts and passwords live in the database and are managed in the app (Team page); changing these variables does nothing |
| `JWT_SECRET` | Random 32+ characters. **The app refuses to start in production without one** (Render can generate it). Changing it signs everyone out |
| `ENABLE_DOCS` | Leave unset. `true` exposes `/docs` (API explorer); keep it off in production |
| `LOGIN_MAX_FAILURES` (5), `LOGIN_WINDOW_MINUTES` (15), `LOGIN_IP_MAX_FAILURES` (20) | Sign-in lockout tuning |
| `AUTOMATION_HOURS_START` (8), `AUTOMATION_HOURS_END` (19), `LOCAL_UTC_OFFSET_HOURS` (1) | When automatic campaigns may send (Lagos time) |
| `CORS_ORIGINS` | The app's own https URL (dashboard is served by the same service) |
| `WA_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_APP_SECRET`, `WA_VERIFY_TOKEN` | WhatsApp Cloud API. Empty `WA_TOKEN` = test mode (nothing is sent). **Set `WA_APP_SECRET` before `WA_TOKEN`**: with a token and no secret the webhook refuses all events |

## Deploy / redeploy
Render builds from branch `phase1-crm` (auto-deploy on push). Health check: `/health` (app) and `/health/db` (database; point the uptime monitor here). Rollback: Render dashboard → Events → redeploy the previous commit.

## Accounts and security
- Everyone signs in with their own email and password (Team page). Passwords are stored only as salted scrypt hashes, minimum 10 characters, with common and name-based passwords refused.
- **Lockout:** 5 wrong passwords for one email (or 20 from one address) within 15 minutes locks sign-in for that window, for the right password too. It clears by itself, or immediately when the person next signs in correctly after the window.
- Changing a password, resetting one, or deactivating someone **signs them out everywhere** immediately.
- **Forgotten password:** an administrator resets it in Team → Edit. **Every administrator locked out:** in Render → the service → Shell, run `python -m scripts.reset_admin someone@kamilightglobal.com`, which asks for a new password and makes that account an active administrator.
- Responses carry strict security headers (CSP, frame blocking, no-store on API data, HSTS on https). `/docs` is off. CSV exports neutralise spreadsheet formulas. Attachment links must be `http(s)`.
- Secrets live only in Render's environment variables. Rotate the Supabase password, WhatsApp token and `JWT_SECRET` periodically, and immediately if ever pasted into a chat or email.

## Automations (Automations page)
Three rules, **off until an administrator switches them on**: *Win back past customers* (status Dormant, opted in), *Follow up on quotes* (quoted, not booked, N days after the quote), *Welcome new enquiries* (first WhatsApp message, once). A background pass runs every 5 minutes, only 08:00-19:00 Lagos time, caps each rule at its daily limit, and never messages the same person twice within the cool-down. Messages go through the normal campaign engine, so each day's run appears under Campaigns as `Auto: <rule> (<date>)` with delivery, read and reply counts, and consent, STOP and test mode are honoured. With WhatsApp live, the marketing rule also needs an approved template name. To pause everything instantly: switch the rule off.

## Go live with WhatsApp
1. KGL's Meta business verified, number added, display name approved.
2. Set `WA_APP_SECRET`, `WA_PHONE_NUMBER_ID`, `WA_VERIFY_TOKEN`, then `WA_TOKEN`. The dashboard's "Test mode" banner disappears.
3. Meta → WhatsApp → Configuration: callback `https://<service>/api/webhooks/whatsapp`, the verify token, subscribe to `messages`.
4. Submit marketing templates; enter each approved name in the campaign builder.
5. First campaign to a small segment; check delivered/read counts and the fee estimate.

## Keep-awake job (free Render)
A Supabase `pg_cron` job named `kgl-keepalive` calls `https://kgl-crm.onrender.com/healthz` every 5 minutes (`select net.http_get(...)`), so the free instance never idles for 15 minutes. Check it: `select * from cron.job_run_details order by start_time desc limit 5;` and `select status_code from net._http_response order by created desc limit 5;`. Stop it: `select cron.unschedule('kgl-keepalive');`. If the service URL changes, re-schedule with the new URL. Not needed on the Starter plan.

## Backups (free Supabase)
Supabase dashboard → Database → Backups is unavailable on free; export with `pg_dump "<direct or pooler URL>" --no-owner -Fc -f kgl-YYYYMMDD.dump` (client major version must match the server: 17) or the dashboard's table export, and store off the laptop. Test a restore into a scratch project.

## Troubleshooting
| Symptom | Check |
|---|---|
| Dashboard won't load / 502 | Render logs; `/health`; is the instance asleep (must be Starter, not Free)? |
| Login fails | `ADMIN_EMAIL` / `ADMIN_PASSWORD` env vars (case-sensitive) |
| `/health/db` returns 503 | Supabase paused or password changed; resume the project, update `DATABASE_URL` |
| Campaign stuck "sending" | Only one instance must run; check logs for `Worker tick failed`; WhatsApp token expired → recipients show failed with Meta's error |
| Customers can't be messaged | Marketing needs opt-in; look at the exclusions list in the campaign preview |
| Duplicate messages | Instance count must be 1 |

## Local development / tests
`crm/backend`: `.venv\Scripts\python -m pytest` (SQLite) or with `TEST_DATABASE_URL=postgres://...` (Postgres). `crm/frontend`: `npm run build`. Browser end-to-end (56 steps, fresh throwaway database; never run it against a real one): `cd crm/e2e && npm install && .\start-e2e.ps1 && npm test`. Read-only check of a deployed site: `E2E_PASSWORD=... BASE_URL=https://... node smoke-live.mjs`.
