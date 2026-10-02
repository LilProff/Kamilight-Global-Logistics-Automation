# Cost: KGL Customer Growth System

Prices checked September 2026; verify on the live pricing pages before committing spend. ₦1,350 = $1.

## Hosting (monthly)
| Item | Plan | USD | NGN | Notes |
|---|---|---|---|---|
| Render web service `kgl-crm` | **Free** + keep-awake ping | 0 | 0 | Free instances sleep after 15 min idle. A Supabase `pg_cron` job pings `/healthz` every 5 min so it stays up (one free service fits the 750 free hours/month). Upgrade to Starter ($7, ≈9,450) for a guaranteed always-on instance |
| Supabase Postgres | Free (decided for launch) | 0 | 0 | **Risk below.** Pro is $25 (≈33,750) |
| n8n on WebSpaceKit | already paid | 0 | 0 | existing |
| Render workspace | Hobby (1 member) | 0 | 0 | Pro $25 only if a second member needs access |
| **Total** | | **0** | **0** | $7 with Starter; $32 (≈43,200) with Starter + Supabase Pro |

## Pass-through (paid by KGL)
- WhatsApp (Meta, from 1 Oct 2026): ≈₦84 per marketing message, ≈₦14 per utility message. The campaign builder shows the exact fee before sending.
- Email: Brevo free plan (300/day). SMS: provider rates when added.
- AI (Phase 2): ≈₦27,000-81,000/month usage-based. Log cost per active user from day one.

## Known risks of the chosen setup (state once, bluntly)
1. **Free Supabase has no backups and pauses on inactivity.** The app queries the database constantly so it will not look inactive, but there is no restore point. Mitigation chosen by the owner: manual exports. The architecture rules for client systems require Pro-tier backups for customer data (NDPR); upgrade trigger: first live campaign data or any customer complaint about lost data.
2. Free projects are limited to 2 active per account and carry no support or uptime guarantee.
3. **Free Render can still go to sleep or restart** (platform maintenance, a missed ping). The sender and webhook stall until the next ping wakes it (about 1 minute); Meta retries missed webhooks. This is the accepted trade-off of $0 hosting; the rules file forbids sleeping hosts for client webhooks, so move to Starter ($7) as soon as KGL's live traffic matters.
4. Free Render 512 MB RAM / 0.1 CPU is plenty for this app; free instances **block outbound SMTP**, so email campaigns must use an HTTP email API (Brevo API) when email is added, not SMTP.
5. Render offers no uptime guarantee on any plan; add an external monitor on `/health/db` for alerts.

## Upgrade triggers
| Trigger | Action | Cost |
|---|---|---|
| Real customer data in production | Supabase Pro (backups, no pausing) | +$25 |
| Second person needs Render access | Render Pro | +$25 |
| >100k messages/month or slow sends | Split the sender into a worker service | +$7 |
| Latency complaints | none needed: always-on already |  |
