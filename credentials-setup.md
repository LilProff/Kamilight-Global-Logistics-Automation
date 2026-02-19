# Credentials Setup Guide

## 1. WhatsApp Cloud API

1. Go to https://developers.facebook.com
2. Create App → Business → Add "WhatsApp" product
3. Go to WhatsApp > API Setup
4. Copy:
   - Phone Number ID
   - WhatsApp Business Account ID
   - Temporary Access Token (or generate permanent via System User)
5. In n8n → Credentials → Create "HTTP Header Auth"
   - Name: `WhatsApp Cloud API`
   - Header: `Authorization`
   - Value: `Bearer YOUR_TOKEN_HERE`

**Webhook for incoming messages (Phase 3):**
- Callback URL: `https://your-n8n.domain.com/webhook/whatsapp`
- Verify Token: set any string, save it — you'll enter same in n8n

---

## 2. Telegram Bot

1. Open Telegram → search @BotFather
2. Send `/newbot` → follow prompts → get BOT_TOKEN
3. Get your admin Chat ID:
   - Message the bot
   - Visit: `https://api.telegram.org/botYOUR_TOKEN/getUpdates`
   - Copy the `chat.id` value
4. In n8n → Credentials → Create "Telegram API"
   - Token: paste BOT_TOKEN

---

## 3. Google Sheets (Service Account)

1. Go to https://console.cloud.google.com
2. Create Project: "Kamilight Automation"
3. Enable APIs:
   - Google Sheets API
   - Google Drive API
4. Create Service Account:
   - IAM → Service Accounts → Create
   - Name: `n8n-automation`
   - Download JSON key file
5. In your Google Sheet → Share → paste service account email (ends in `@...gserviceaccount.com`) → Editor
6. In n8n → Credentials → Create "Google Sheets OAuth2 API" using the JSON key

---

## 4. Apollo.io (Phase 2)

1. Sign up at https://app.apollo.io
2. Go to Settings → Integrations → API
3. Generate API Key
4. In n8n → Credentials → Create "HTTP Header Auth"
   - Name: `Apollo.io API`
   - Header: `x-api-key`
   - Value: `YOUR_API_KEY`

---

## 5. n8n Setup (Self-Hosted)

### Docker on Ubuntu VPS:

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Run n8n
docker run -d \
  --name n8n \
  -p 5678:5678 \
  -e N8N_BASIC_AUTH_ACTIVE=true \
  -e N8N_BASIC_AUTH_USER=admin \
  -e N8N_BASIC_AUTH_PASSWORD=STRONG_PASSWORD \
  -e WEBHOOK_URL=https://your-domain.com/ \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n

# Set up Nginx reverse proxy
# SSL via: certbot --nginx -d your-domain.com
```

---

## Environment Variables Template

See `shared/config/env.template.json` for all required values.
Never commit real credentials to this repo.
