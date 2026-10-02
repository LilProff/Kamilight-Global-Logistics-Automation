# Cost: KGL Customer Growth System

Prices checked September 2026; verify on the live pricing pages before committing spend. ₦1,350 = $1.

## Hosting (monthly)
| Item | Plan | USD | NGN | Notes |
|---|---|---|---|---|
| Render web service `kgl-crm` | Starter (always on) | 7 | ≈9,450 | Required: sender + webhooks. Free tier sleeps. |
| Supabase Postgres | Free (decided for launch) | 0 | 0 | **Risk below.** Pro is $25 (≈33,750) |
| n8n on WebSpaceKit | already paid | 0 | 0 | existing |
| Render workspace | Hobby (1 member) | 0 | 0 | Pro $25 only if a second member needs access |
| **Total** | | **7** | **≈9,450** | $32 (≈43,200) with Supabase Pro |

## Pass-through (paid by KGL)
- WhatsApp (Meta, from 1 Oct 2026): ≈₦84 per marketing message, ≈₦14 per utility message. The campaign builder shows the exact fee before sending.
- Email: Brevo free plan (300/day). SMS: provider rates when added.
- AI (Phase 2): ≈₦27,000-81,000/month usage-based. Log cost per active user from day one.

## Known risks of the chosen setup (state once, bluntly)
1. **Free Supabase has no backups and pauses on inactivity.** The app queries the database constantly so it will not look inactive, but there is no restore point. Mitigation chosen by the owner: manual exports. The architecture rules for client systems require Pro-tier backups for customer data (NDPR); upgrade trigger: first live campaign data or any customer complaint about lost data.
2. Free projects are limited to 2 active per account and carry no support or uptime guarantee.
3. Render offers no uptime guarantee on Starter; use an external monitor on `/health/db`.

## Upgrade triggers
| Trigger | Action | Cost |
|---|---|---|
| Real customer data in production | Supabase Pro (backups, no pausing) | +$25 |
| Second person needs Render access | Render Pro | +$25 |
| >100k messages/month or slow sends | Split the sender into a worker service | +$7 |
| Latency complaints | none needed: always-on already |  |
