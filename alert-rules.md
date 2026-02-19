# Monitoring & Alert Rules — Kamilight Automation

## Monitoring Stack (All Free or Near-Free)

| Tool | Purpose | Cost |
|------|---------|------|
| UptimeRobot | Monitor n8n is alive | Free |
| n8n built-in logs | Execution history | Built-in |
| Google Sheets Errors tab | Failed sends | Free |
| Telegram bot | Real-time admin alerts | Free |

---

## Alert Rules

### Immediate Alerts (Send to Admin Telegram Now)

| Trigger | Message |
|---------|---------|
| n8n server unreachable | UptimeRobot sends email/SMS |
| Broadcast fails > 10% contacts | ⚠️ Broadcast had high failure rate. Check Errors tab. |
| Google Sheets unreachable | ❌ Cannot read Sheets. Check Google API credentials. |
| WhatsApp API returns 401 | ❌ WhatsApp token expired. Regenerate access token. |
| Incoming reply received | 📩 Reply from {name}: "{message}" |

### Daily Summary (8AM Telegram Message)

```
📊 Daily Summary — Kamilight Automation
━━━━━━━━━━━━━━━━━━━━━
Yesterday:
• Broadcasts sent: X
• Follow-ups sent: X  
• Replies received: X
• Failed sends: X

Pending:
• Follow-ups due today: X
• Leads in sheet: X (Contacts) + X (Leads)
━━━━━━━━━━━━━━━━━━━━━
```

---

## Error Tab Structure in Google Sheets

Headers: Timestamp | Phone | Error Message | Workflow | Retry Count

Review this tab weekly. Common errors:
- Invalid phone number → fix in Contacts tab
- WhatsApp API 400 → phone not on WhatsApp
- WhatsApp API 401 → token expired

---

## n8n Execution Monitoring

- In n8n UI: Executions → filter by workflow → check for failed runs
- Set retention: Settings → keep executions for 30 days
- Failed executions turn red — check "Output" panel for error details

---

## Weekly Health Check (Manual, 10 min)

Every Monday:
1. Check Errors tab — any recurring failures?
2. Check n8n executions — any red workflows?
3. Check Contacts tab — add new contacts, update stale tags
4. Review replies — update Response Status for anyone who replied
5. Check WhatsApp token expiry — regenerate if < 7 days left

---

## UptimeRobot Setup

1. Sign up free at uptimerobot.com
2. Add monitor: HTTP(s) → your n8n URL → every 5 min
3. Alert contacts: your email + phone number
4. You'll get notified within 5 min if n8n goes down
