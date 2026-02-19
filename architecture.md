# System Architecture — Kamilight Global Logistics Automation

## Architecture Diagram (Text)

```
ADMIN (Telegram)
     │
     │  /broadcast [tag] [message]
     ▼
┌─────────────────┐
│   n8n Engine    │  ← self-hosted on VPS (Ubuntu + Docker)
│  (Orchestrator) │
└────────┬────────┘
         │
    ┌────▼─────────────────────────┐
    │       Google Sheets          │
    │  (Customer + Lead Database)  │
    └────┬─────────────────────────┘
         │  filter by tag
         │  loop contacts
         ▼
┌─────────────────────┐
│  WhatsApp Cloud API │  → Customer receives message
└─────────────────────┘
         │
         ▼ (future)
┌─────────────────────┐
│  Response Listener  │  → Telegram notifies admin
└─────────────────────┘
```

---

## Component Responsibilities

### 1. Telegram Bot (Admin Interface)
- Receives commands from admin
- Parses: target tag + message content
- No AI, no decision making — pure command relay
- Commands defined in Phase 1

### 2. n8n (Automation Engine)
- Self-hosted on a cheap VPS ($5–10/mo on Hetzner or DigitalOcean)
- Receives Telegram webhook
- Reads Google Sheets
- Filters contacts by tag
- Loops and sends WhatsApp messages
- Logs results
- Handles errors and retries

### 3. Google Sheets (Database)
- Single source of truth for all contacts
- Always fetched fresh — no caching
- Columns defined in `shared/schemas/contacts-sheet-schema.json`
- Multiple tabs: Contacts, Leads, Logs, Config

### 4. WhatsApp Cloud API
- Used via Meta Developer portal
- Messages sent per-contact (no broadcast list needed)
- Supports text and image
- Rate limit: ~80 messages/second (more than enough)

### 5. Apollo.io (Phase 2)
- External lead source
- Queried via REST API
- Results piped into Sheets automatically

---

## n8n Hosting Recommendation

**Option A (Cheapest — recommended to start):**
- Hetzner Cloud CX11: 2 vCPU, 2GB RAM — ~€4.5/mo
- Docker + n8n + Nginx
- SSL via Certbot (free)

**Option B (Managed):**
- n8n.cloud — $20/mo
- No server management, easier to start
- Switch to self-hosted when volume grows

---

## Data Flow Per Phase

### Phase 1 — Broadcast
```
Telegram command → n8n trigger → fetch Sheet → filter tag
→ loop contacts → POST WhatsApp API → log result → Telegram confirmation
```

### Phase 2 — Lead Gen
```
Cron (daily) → n8n → Apollo API → parse leads → append to Sheet
→ auto-tag based on score → ready for broadcast
```

### Phase 3 — Follow-up
```
Cron (hourly) → n8n → read Sheet → find contacts where:
  Last Contacted < (today - interval) AND Stage != "closed"
→ send WhatsApp → update Last Contacted → log
```

### Phase 4 — Lifecycle
```
Cron (weekly/monthly) → n8n → read Sheet → filter by Stage
→ send relevant message → update engagement score
```

---

## Security Considerations

- All API keys stored in n8n credential vault (never in workflows)
- Telegram bot restricted to admin chat ID only
- WhatsApp API token rotated every 60 days
- Google Sheets access via Service Account (not personal Google account)
- n8n instance behind Nginx with basic auth or IP whitelist

---

## Failure Handling

| Failure Point | Strategy |
|---|---|
| WhatsApp API timeout | n8n retry (3x with backoff) |
| Sheet read fails | Abort + Telegram alert to admin |
| Invalid phone format | Skip + log to Error tab in Sheet |
| Rate limit hit | n8n Wait node (delay loop) |
| n8n server down | UptimeRobot alert (free) |

---

## Monitoring

- n8n built-in execution logs (keep 30 days)
- UptimeRobot (free) watching n8n URL
- Telegram bot sends daily summary to admin
- Error tab in Google Sheets for failed sends
- All successful sends logged to Logs tab with timestamp
