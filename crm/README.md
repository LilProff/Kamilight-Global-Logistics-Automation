# KGL Customer Growth System: Phase 1

The customer database and broadcast centre KGL asked for.

- **Customer database:** one profile per customer: contact details, customer type, routes, goods, shipments, spend, source, marketing consent, notes, and a timeline of every message, campaign, quote and shipment.
- **Automatic statuses:** New enquiry → Quoted → Booked → Repeat → VIP, plus Dormant (60+ days without shipping, checked daily) and Lost. Staff can override any status.
- **Import:** KGL's Excel/CSV lists. Columns are matched automatically, phone numbers cleaned to +234…, duplicates merged, and the old Google Sheets tags (`active client`, `past client`, `do not contact`…) mapped to the new statuses.
- **Filters and segments:** filter by status, route, customer type, days since last shipment, number of shipments, spend, city, tags, source, staff. Save any filter as a segment.
- **Broadcast and campaign centre:** pick a segment or filters, see who will receive the message and the Meta fee before sending, write a personalised message (`{first_name}`, `{city}`…) with an image, video or PDF, then send now or schedule. Messages go out at a steady pace and delivery, read and reply counts are reported per campaign.
- **Compliance built in:** WhatsApp marketing only goes to customers who agreed to it; "STOP" replies opt people out instantly; do-not-contact is never messaged. Marketing uses Meta-approved templates.
- **WhatsApp webhook:** delivery and read receipts, inbound replies on the customer timeline, and new numbers that message KGL become new enquiries automatically.

**Test mode:** until KGL's WhatsApp Business credentials are added, everything runs end to end but nothing is actually sent. The dashboard shows a banner.

## Run locally

```bash
# Backend (Python 3.12)
cd crm/backend
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env          # then set ADMIN_PASSWORD and JWT_SECRET
.venv\Scripts\python -m scripts.seed_demo      # optional: 80 sample customers tagged 'demo'
.venv\Scripts\python -m uvicorn app.main:app --port 8000

# Dashboard
cd crm/frontend
npm install
npm run dev                     # http://localhost:5173
```

Remove demo data with `python -m scripts.seed_demo --remove`. Run the tests with `.venv\Scripts\python -m pytest`.

## Deploy (Render + Supabase)

1. **Supabase:** create a project (free plan is fine; the app queries the database constantly, so it never counts as inactive and won't be paused). Copy the **Session pooler** connection string (Project Settings > Database).
2. **Render:** New > Blueprint > this repo, branch `phase1-crm`. It reads `render.yaml` and creates the always-on `kgl-crm` service (Starter plan, one instance: the campaign sender runs inside it, so never scale it past one).
3. Enter the secrets Render asks for: `DATABASE_URL` (the Supabase string), `ADMIN_EMAIL`, `ADMIN_PASSWORD`. Leave the `WA_*` values blank until WhatsApp is connected.
4. Tables are created automatically on first start. Monitor `https://<service>/health/db`.

Free Supabase has no automatic backups: export the database from the Supabase dashboard from time to time.

Alternative: `docker compose up -d --build` in `crm/` runs the same image on any server (SQLite by default, or set `DATABASE_URL`).

## Connect WhatsApp (when KGL's Meta access arrives)

1. In Meta Business Manager, create the WhatsApp Business app and add KGL's dedicated number.
2. Set `WA_TOKEN` (permanent system-user token), `WA_PHONE_NUMBER_ID`, `WA_APP_SECRET` and a `WA_VERIFY_TOKEN` in `.env`, then restart.
3. Webhook URL: `https://crm.<domain>/api/webhooks/whatsapp` with the same verify token. Subscribe to `messages`.
4. Submit KGL's marketing templates for approval in Meta Business Manager (starting points in `../message-examples.md`), then enter each approved template's name in the campaign builder.

## Where this goes next (Phase 2)

AI sales assistant on inbound WhatsApp messages, rate card and instant quotes, automated follow-up sequences, and the n8n Telegram bot calling this API instead of Google Sheets.
