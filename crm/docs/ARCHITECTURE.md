# Architecture: KGL Customer Growth System (Phase 1)

Context: **B, client system** (see the architecture rules): go-live is paid, always-on infrastructure; no free tier that pauses, sleeps or lacks backups for live customer data.

```
 Staff browser ──HTTPS──▶  Render web service "kgl-crm"  (Docker, Starter, 1 instance, always on)
 (React dashboard,          ├─ FastAPI  /api/*            REST for the dashboard (JWT login)
  served by FastAPI)        ├─ /api/webhooks/whatsapp     Meta webhook: signature-checked, duplicate-proof
                            ├─ background worker thread   starts scheduled campaigns, sends at 10 msg/s,
                            │                             marks customers dormant daily
                            └─ SQLAlchemy ──▶ Supabase Postgres (session pooler, port 5432)
 WhatsApp Cloud API  ◀── campaign sender            ▲  RLS on, public API roles revoked
 Meta webhooks ─────────▶ /api/webhooks/whatsapp ───┘
 n8n (WebSpaceKit, already paid) ── existing Telegram bot / automations (Phase 2: call this API)
```

## Why this shape (tiers from the rules)

| Piece | Tier | Reason |
|---|---|---|
| Customer data, filters, segments | Postgres (Supabase) | Plain CRUD data; RLS blocks the public API |
| API + dashboard + sender + webhook | **D: always-on host** | A background sender and WhatsApp webhooks must stay awake. Scale-to-zero (tier C) would throttle CPU after each response and stall queued messages; sleeping free hosts are forbidden for webhooks |
| Dashboard (React/Vite) | served by the same container | Avoids Vercel Hobby (non-commercial) and a second deployment; one image runs anywhere |

Alternatives considered and rejected: Supabase-only (pg_cron + Edge Functions) would need a rewrite for no cost win (the host is $7/month); Cloud Run min-instances 0 stalls the in-process sender; Next.js adds nothing (no SEO need). No rewrite is planned.

## Data model (5 core tables + 1)
`contacts` (profile, status, consent, totals) · `contact_events` (timeline) · `segments` (saved filters) · `campaigns` · `campaign_recipients` (frozen audience + delivery status) · `webhook_events` (processed WhatsApp message ids).

## Key behaviours
- **Consent:** WhatsApp *marketing* only reaches customers with recorded opt-in; STOP opts out instantly and permanently; do-not-contact always excluded; rechecked at send time.
- **Statuses:** new → quoted → booked → repeat → vip, plus dormant (no shipment in 60 days, daily sweep) and lost. Derived from shipments; staff can override.
- **Single instance:** the sender runs in-process. Never scale `numInstances` above 1 or messages double-send. If volume ever needs more, split the sender into a worker service first.
- **Security:** RLS enabled and `anon`/`authenticated` rights revoked on every table at startup; webhook signatures mandatory once WhatsApp is live; secrets only in Render env vars; CORS limited to configured origins; no wildcard with credentials.

## Phase 2 hooks
AI sales assistant on inbound messages (`inbound.handle_message`), rate card/quotes, follow-up sequences, and the Telegram bot calling this API instead of Google Sheets.
