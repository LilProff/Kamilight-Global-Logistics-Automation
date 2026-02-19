# Scaling Guide

## When to Scale

| Signal | Action |
|--------|--------|
| > 500 contacts in Sheet | Add pagination to Sheet reads |
| > 1000 messages/day | Upgrade VPS RAM or switch to n8n cloud |
| Sheet becoming slow | Migrate to Airtable or Supabase |
| Multiple admins needed | Add role system in Config tab |
| Need AI replies | Integrate OpenRouter in Phase 3 |
| Multi-channel (Email + WA) | Add SendGrid node to Phase 4 |

## Phase-by-Phase Scaling Path

### Phase 1 Scaling
- Add message queue (n8n's built-in queue mode) when contacts > 1000
- Implement batch delay: send 50 messages, wait 30s, repeat
- Use WhatsApp template messages for higher limits

### Database Scaling (from Sheets to Supabase)
When Google Sheets becomes too slow (usually > 5000 rows):
1. Create Supabase project (free tier is generous)
2. Mirror the schema
3. Update n8n nodes from "Google Sheets" to "Postgres" 
4. Migration script included in `shared/utils/`

### n8n Scaling
- Enable queue mode: add Redis + worker nodes
- Move to n8n cloud if server management is a burden
- Separate workflows by phase on different triggers

## Cost Projection

| Contacts | VPS | n8n | Estimate/month |
|----------|-----|-----|----------------|
| 0–500 | Hetzner CX11 €4.5 | Self-hosted | ~$10 |
| 500–2000 | Hetzner CX21 €8 | Self-hosted | ~$15 |
| 2000–10000 | Hetzner CPX31 €15 | Self-hosted | ~$25 |
| 10000+ | Dedicated or n8n cloud | n8n cloud $50 | ~$70 |

WhatsApp costs are separate (Meta charges per conversation).
