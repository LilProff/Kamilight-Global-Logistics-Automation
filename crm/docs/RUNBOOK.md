# Runbook: KGL Customer Growth System

## Environment variables (Render dashboard; never commit)
| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Supabase **session pooler** string (port 5432, user `postgres.<ref>`). Not the direct address (IPv6 only) and not port 6543 |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Staff login |
| `JWT_SECRET` | Random 48+ chars (Render can generate) |
| `CORS_ORIGINS` | The app's own https URL (dashboard is served by the same service) |
| `WA_TOKEN`, `WA_PHONE_NUMBER_ID`, `WA_APP_SECRET`, `WA_VERIFY_TOKEN` | WhatsApp Cloud API. Empty `WA_TOKEN` = test mode (nothing is sent). **Set `WA_APP_SECRET` before `WA_TOKEN`**: with a token and no secret the webhook refuses all events |

## Deploy / redeploy
Render builds from branch `phase1-crm` (auto-deploy on push). Health check: `/health` (app) and `/health/db` (database; point the uptime monitor here). Rollback: Render dashboard → Events → redeploy the previous commit.

## Go live with WhatsApp
1. KGL's Meta business verified, number added, display name approved.
2. Set `WA_APP_SECRET`, `WA_PHONE_NUMBER_ID`, `WA_VERIFY_TOKEN`, then `WA_TOKEN`. The dashboard's "Test mode" banner disappears.
3. Meta → WhatsApp → Configuration: callback `https://<service>/api/webhooks/whatsapp`, the verify token, subscribe to `messages`.
4. Submit marketing templates; enter each approved name in the campaign builder.
5. First campaign to a small segment; check delivered/read counts and the fee estimate.

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
`crm/backend`: `.venv\Scripts\python -m pytest` (SQLite) or with `TEST_DATABASE_URL=postgres://...` (Postgres). `crm/frontend`: `npm run build`. Browser end-to-end: start the backend on a fresh SQLite DB and Vite, then `cd crm/e2e && npm install && npm test`.
