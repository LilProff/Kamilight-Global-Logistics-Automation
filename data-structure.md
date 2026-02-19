# Data Structure — Google Sheets Schema

## Sheet Tabs Overview

```
Workbook: Kamilight CRM
├── Contacts          ← main customer database
├── Leads             ← cold leads from Apollo or manual
├── Logs              ← every message sent (auto-populated)
├── Errors            ← failed sends (auto-populated)
└── Config            ← settings, broadcast templates, intervals
```

---

## Tab 1: Contacts

| Column | Header | Type | Notes |
|--------|--------|------|-------|
| A | ID | Auto (row number) | Use ROW()-1 formula |
| B | Name | Text | Full name |
| C | Phone | Text | Include country code, e.g. +2348012345678 |
| D | Company | Text | Business name |
| E | Tag | Text | See Tag Taxonomy below |
| F | Stage | Text | lead / prospect / active / past / churned |
| G | Source | Text | referral / apollo / manual / telegram |
| H | Last Contacted | Date | Updated by automation on each send |
| I | Follow-up Due | Date | Calculated: Last Contacted + interval days |
| J | Response Status | Text | no_reply / responded / interested / not_interested |
| K | Notes | Text | Free text, manual |
| L | Assigned To | Text | Sales rep name (future use) |
| M | Created Date | Date | Row creation date |
| N | WhatsApp Opt-Out | Boolean | TRUE = never message |

---

## Tab 2: Leads (Cold Leads from Apollo)

Same columns as Contacts, plus:
| O | Apollo ID | Text | Apollo lead ID for deduplication |
| P | Lead Score | Number | 1–100 from Apollo |
| Q | Industry | Text | logistics / manufacturing / retail / etc |
| R | Country | Text | |
| S | Email | Text | For future email outreach |

---

## Tab 3: Logs

| Column | Header |
|--------|--------|
| A | Timestamp |
| B | Contact Name |
| C | Phone |
| D | Tag |
| E | Message Sent |
| F | Status (sent/failed) |
| G | Workflow |

---

## Tab 4: Errors

| Column | Header |
|--------|--------|
| A | Timestamp |
| B | Phone |
| C | Error Message |
| D | Workflow |
| E | Retry Count |

---

## Tab 5: Config

| Column | Header | Example Value |
|--------|--------|---------------|
| A | Key | follow_up_interval_days |
| B | Value | 7 |
| C | Description | Days before auto follow-up triggers |

Config keys:
- `follow_up_interval_days` — default: 7
- `broadcast_delay_ms` — delay between messages to avoid spam flags: 1000
- `admin_telegram_id` — Telegram user ID of admin
- `active_phases` — which phases are running: 1,2,3

---

## Tag Taxonomy

Tags must be EXACT strings. Case-sensitive. Only one tag per contact.

| Tag | Meaning | Who Gets This |
|-----|---------|---------------|
| `potential client` | Not yet approached | New contacts, not yet contacted |
| `high potential` | Shown interest or referred | Hot uncontacted leads |
| `active client` | Currently using services | Paying customers |
| `past client` | Used services before, lapsed | Win-back targets |
| `cold` | Auto-tagged from Apollo, no engagement | Apollo imports |
| `warm` | Replied or clicked previously | Engaged but not converted |
| `do not contact` | Opt-out or blocked | Never target in any broadcast |

---

## Tagging Rules

1. Every contact MUST have exactly one tag
2. Tag drives ALL automation logic
3. Tag should be updated manually or by automation after a response
4. `do not contact` overrides everything — always filter these out

---

## Phone Number Format Standard

All phone numbers must be stored in E.164 format:
- Include country code
- No spaces, dashes, or parentheses
- Examples: `+2348012345678`, `+447911123456`

The `phone-formatter.js` utility in `shared/utils/` handles normalization.

---

## Recommended Google Sheets Settings

- Freeze row 1 (headers) in all tabs
- Lock columns A, M, N from manual editing
- Share with: n8n Service Account (Editor), Admin (Editor)
- Enable Version History (automatic in Google)
- Tab color coding: Contacts=Blue, Logs=Green, Errors=Red
