# Phase 1 — WhatsApp Broadcast System

## How It Actually Works

The admin talks to a **Telegram bot**. The bot walks them through the broadcast in steps — no commands to memorize, no special syntax. Just a conversation.

```
┌─────────────────────────────────────────────────────┐
│              ADMIN EXPERIENCE                        │
│                                                      │
│  Admin → "hey" (or anything)                        │
│                                                      │
│  Bot  → "Who should receive this?                   │
│          1️⃣ Major Clients                           │
│          2️⃣ Existing Clients                        │
│          3️⃣ Potential Clients                       │
│          4️⃣ Past Clients                            │
│          5️⃣ ALL Contacts"                           │
│                                                      │
│  Admin → taps "2️⃣ Existing Clients"                │
│                                                      │
│  Bot  → "Segment selected: EXISTING CLIENTS         │
│          Now send your broadcast content ↓"         │
│                                                      │
│  Admin → sends a flyer image + caption              │
│          "New routes available! Book now."          │
│                                                      │
│  Bot  → "📋 Preview:                               │
│          🎯 Segment: EXISTING CLIENTS               │
│          👥 Recipients: 47 contacts                 │
│          🖼️ Image with caption: New routes...       │
│          Ready? [✅ YES SEND IT] [❌ CANCEL]"        │
│                                                      │
│  Admin → taps "✅ YES SEND IT"                      │
│                                                      │
│  Bot  → "🚀 Broadcast started! Sending to 47..."   │
│          [n8n loops, sends WhatsApp DMs]             │
│                                                      │
│  Bot  → "✅ Broadcast Complete!                     │
│          Segment: EXISTING CLIENTS                  │
│          Sent: 47 contacts | Format: image          │
│          11:43 AM WAT, 19 Feb 2026"                 │
└─────────────────────────────────────────────────────┘
```

---

## Segments Available

| Option | Tag in Sheet | Who Receives |
|--------|-------------|--------------|
| 1️⃣ Major Clients | `major client` | Top-tier, highest value clients |
| 2️⃣ Existing Clients | `existing client` | All active current clients |
| 3️⃣ Potential Clients | `potential client` | Leads not yet converted |
| 4️⃣ Past Clients | `past client` | Former clients, win-back targets |
| 5️⃣ ALL Contacts | `all` | Everyone (minus opt-outs + do-not-contact) |

---

## Content Types Supported

The bot accepts **whatever the admin sends** after choosing a segment:

| Admin sends | WhatsApp receives |
|-------------|------------------|
| A text message | Text message |
| A photo/flyer | Image message |
| A photo + caption | Image with caption |
| A video | Video |
| A video + caption | Video with caption |
| A PDF or Word doc | Document |
| A PDF + caption | Document with caption |
| A voice note | Audio message |

**No limits on what you send.** Ads, announcements, thank-you fliers, rate sheets, offers, videos — anything goes through this system unchanged.

---

## What Gets Blocked

Contacts are automatically skipped if:
- Tag is `do not contact`
- `WhatsApp Opt-Out` column is `TRUE`
- Phone number is missing or invalid

---

## New Google Sheets Tab Required: Session

The bot remembers where the admin is in the broadcast flow using a **Session tab** in the Google Sheet.

Create this tab with these exact headers:

```
admin_chat_id | step | selected_segment | content_type | content_text | media_file_id | media_caption | media_type | started_at | status
```

This tab is managed entirely by the automation. One row is created when a broadcast starts, updated as the admin progresses, and marked `done` when complete.

---

## Files in This Folder

| File | What It Is |
|------|-----------|
| `workflows/broadcast-trigger.json` | Main n8n workflow — import this |
| `scripts/media-send-guide.md` | Step-by-step for the 3-node media upload pattern |
| `templates/message-examples.md` | Ready-to-send message templates per segment |

---

## Setup Checklist

```
□ Create 'Session' tab in Google Sheet (headers above)
□ Add to Logs tab: Segment Targeted, Content Type, Caption/Message
□ Get your Telegram Chat ID (message @userinfobot)
□ Get your WhatsApp Phone Number ID from Meta Developer dashboard
□ Get your Telegram Bot Token from @BotFather
□ In n8n: create 3 credentials:
    - Telegram Bot API (token)
    - Google Sheets (service account JSON)
    - HTTP Header Auth for WhatsApp (Authorization: Bearer YOUR_TOKEN)
□ Import broadcast-trigger.json into n8n
□ Replace 4 placeholders in the workflow:
    YOUR_ADMIN_TELEGRAM_CHAT_ID
    YOUR_GOOGLE_SHEET_ID
    YOUR_PHONE_NUMBER_ID
    YOUR_BOT_TOKEN
□ Activate workflow
□ Test: message bot → pick segment → send "test message" → confirm
```
