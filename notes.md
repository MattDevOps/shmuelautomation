# Shmuel Classic Jerusalem Realty — Project Notes

Internal working notes. Everything in `client/` is what Shmuel sees.

---

## Client

- **Shmuel**, close friend of mine
- Owns **Classic Jerusalem Realty** — real estate brokerage in Jerusalem
- Current website is WordPress, feels slow, design needs modernizing
- He speaks English (no translation needed for comms)
- Stated long-term goal: "build something valuable I can sell one day" (SaaS for brokers)

---

## What he asked for (full scope)

### Property management
- Upload properties manually OR via Yad2 link
- Mark available / rented
- Different groups/lists for rent vs sale

### Auto-posting
- Facebook groups (up to 21 for rentals, different set for sale)
- WhatsApp groups (6 for rentals, different for sale)
- WhatsApp status
- Janglo website (rental section)
- Different groups configurable, editable anytime

### Scheduling
- 3 properties at 8am, 3 at 8pm
- No posts Friday night, all Saturday
- Resume Saturday ~10pm
- New listings get priority in queue
- Follow queue order otherwise

### Data / CRM
- Auto-generated Excel of all properties (owner phone, broker fee status, all details)
- Auto-organized photo folders in cloud storage per property
- WhatsApp catalog sync

### Site improvements
- General design refresh
- Performance optimization
- Multi-language via AI translation

### Phase 2 features (he mentioned as "later")
- AI chatbot for inbound WhatsApp queries (match client needs to listings, with manual takeover)
- AI summarization of phone calls + WhatsApp → CRM
- Newsletter signup + auto-email every 3 new properties

### He mentioned
- A paid app called "webot" aimed at real estate agents — open to integrating vs building from scratch

---

## My analysis — what's doable

### 100% doable, clean
- Property CMS + database
- Scheduling with Shabbat logic (just cron + rules)
- Excel export
- Cloud photo organization
- Email marketing (SendGrid / Resend / Mailchimp)
- AI chatbot for property matching (via official WhatsApp Business API — legit, no ban risk)
- Call + WhatsApp summarization (Twilio + Whisper + GPT → CRM)
- Multi-language via AI translation
- Janglo posting (if they have an API; form automation otherwise)

### Doable but with real risk — DO NOT PROMISE
- **WhatsApp group auto-posting + status automation** — violates WhatsApp ToS. His business number *will* get banned eventually. All solutions (Green-API, Whapi, Selenium, browser bots) carry this risk.
- **Facebook group auto-posting** — Meta killed most of the Groups API path. Browser automation remains but is fragile + ToS-violating.
- **Yad2 scraping** — Cloudflare + bot detection. Will break periodically.
- **WhatsApp catalog sync** — official Business API is limited for rich real-estate data; partial sync only.

### My reframe for the risky parts
- Build a **"one-tap share" system** instead of full automation: the system pre-composes the post (text + photo collage in his format) and opens WhatsApp / Facebook ready to send. He taps send. 5 seconds per post, zero ban risk.
- Manual Yad2 import path always stays; auto-import is best-effort.
- Official WhatsApp Business API for the AI chatbot — this part IS fully legit.

---

## Architecture decision — HYBRID

Don't rebuild from scratch. Don't stack plugins on WordPress.

**Keep WordPress** as public-facing site (preserves SEO, domain authority, already works for visitors).

**Build separate backend service** as the real "brain":
- Python / FastAPI + PostgreSQL
- Source of truth for properties, clients, CRM
- Runs automation engine (scheduler, posting, AI, email)
- WordPress pulls listings from backend via API
- If WordPress ever becomes bottleneck → swap the frontend, backend stays

**Why this wins**:
- Ships fast (weeks not months)
- Preserves his SEO/traffic
- Valuable parts (DB + automation + AI) built clean from day one
- Easy migration path later if he ever goes full product

---

## Phased plan

### Phase 1 — Foundation (4-6 weeks)
- Property database (single source of truth)
- Admin dashboard (upload, edit, mark available/rented, filter)
- Manual Yad2 import
- Auto photo organization in cloud folders
- Auto Excel export
- WordPress integrated as display layer (pulls from DB)
- Site performance cleanup

**End state**: one clean place for everything; still posting manually but much faster.

### Phase 2 — Publishing & Scheduling (3-4 weeks)
- One-tap share system (WhatsApp + Facebook)
- Smart scheduler (8am/8pm, skip Fri night + Saturday, resume Sat 10pm)
- New listings get priority in queue
- Separate queues for rent vs sale; configurable groups
- Janglo posting

**End state**: daily posting work goes from hours to minutes.

### Phase 3 — AI & Client Layer (4-6 weeks)
- AI chatbot on WhatsApp Business API (property matching, manual takeover)
- Call + WhatsApp auto-summarization into CRM
- Newsletter signup + auto-email every N new properties
- Multi-language via AI translation

**End state**: looks 10x more professional than other brokers.

### Phase 4 — Optional (later)
- Multi-tenant the system for other brokers
- Billing, onboarding, admin
- Only if Phase 3 proves out and he's still serious about selling

---

## Pricing

### Total: $6,800 for full build (Phases 1-3)
- Started at $7,000; final $200 off as a favor
- ~75%+ off my normal rate
- Justified by: I build fast with AI assistance, and he's a close friend

### Payment structure (no deposit — friend call)
- **$3,000** — at end of Phase 1
- **$2,000** — at end of Phase 2
- **$1,800** — at end of Phase 3

Total $6,800. No deposit per user's decision. Slightly front-loaded into Phase 1 since it's the longest + most foundational phase. Risk: 4-6 weeks of unpaid work in Phase 1.

### What's NOT in the $7k
- **Infrastructure costs** — Shmuel pays directly on his own credit card. Never on mine.
- **Major new features post-launch** — anything beyond the three phase specs gets scoped and priced when requested (Phase 4 or later).

### Maintenance arrangement (no retainer — friend call)
- Small fixes and bug patches after Phase 3: free, as a friend
- Anything bigger (new features, major changes): scoped + priced case-by-case at the time
- **Risk**: "small fix" can creep. Watch for this in months 3-12 post-launch. If it becomes regular work, revisit and propose a retainer then.

---

## Rules I must follow to not get burned

1. **Scope locked per phase.** One-pager per phase, written down, both agree before work starts. Extras go in a "later" list, not worked on mid-phase.
2. **Maintenance boundary**: small fixes free as a friend; anything bigger is scoped + priced separately. Watch for creep — if "small fixes" become weekly, renegotiate.
3. **Infra accounts are on his card.** All of them. Every time.
4. **Write it down even between friends.** Especially between friends. Saves the friendship when memories differ in month 4.

---

## Ongoing infrastructure costs (Shmuel pays directly)

| Service | Purpose | Cost/mo |
|---|---|---|
| OpenAI API | Chatbot, summaries, translation | $30-150 |
| WhatsApp Business API | Legit 1-on-1 chatbot | $5-40 |
| Twilio | Call recording + transcription (optional) | $20-60 |
| Google Cloud Run | Backend hosting (FastAPI) | $0 (always-free covers single-user traffic; verification card only) |
| Cloudflare Pages | Admin frontend hosting | $0 (free tier) |
| Supabase | Postgres DB | $0-25 |
| Upstash (Phase 2+) | Redis for scheduled posting queue | $0-10 |
| Email (Resend/SendGrid) | Newsletter | $0-30 |
| Google Drive | Property photos (his account) | $0-20 |

**Realistic totals**:
- Month 1-3 (light use): **$50-100/mo**
- Month 4-12 (normal): **$100-200/mo**
- Year 2+ (scaled): **$200-400/mo**

Safe starting budget to tell him: **~$150/mo**, grows with usage.

---

## What's been sent to Shmuel

1. ✅ **Cost breakdown message** — all 6 infra services explained, monthly totals by stage, framed as costs growing with business activity (not overhead)
2. ✅ **Full proposal message** — 3 hard truths upfront (WhatsApp/FB/Yad2 limits), hybrid architecture explanation, 3 phases with deliverables/timelines, what I'm NOT promising, what I need from him to start

**Still to send**:
- Pricing + payment structure ($7k, $2k deposit, milestones)
- Phase 1 detailed scope doc (one-pager)
- Maintenance terms (post-launch retainer)

---

## What I need from Shmuel to start Phase 1

- Access to current WordPress site + hosting
- Google Drive or Dropbox account for photos
- List of Facebook groups (rent + sale)
- List of WhatsApp groups (rent + sale)
- Any existing client/property spreadsheets (so we import, don't lose history)
- Credit card on file for infra accounts (I set up, he pays)

---

## Open items / next steps

- [ ] Send pricing + payment structure message to Shmuel
- [ ] Get his yes on phased approach
- [ ] Collect $2k deposit before starting
- [ ] Draft Phase 1 one-pager spec
- [ ] Both sign off (even informally) on Phase 1 scope
- [ ] Start Phase 1

---

## Tech stack (decided 2026-04-20)

- **Backend**: Python + FastAPI (uv-managed, pytest)
- **DB**: Postgres via **Supabase** (hosted — no local Docker). Treat as plain Postgres; no lock-in to Supabase-specific features (Auth, RLS, etc.) unless a real need shows up.
- **Backend hosting**: **Google Cloud Run** (decided 2026-05-03). Free tier covers single-user traffic; container deployed via `gcloud run deploy`. Same GCP project as Drive OAuth (one less vendor).
- **Queue/scheduler** (Phase 2+): **Upstash** Redis (hosted) + cron workers on Fly. Not needed in Phase 1.
- **Admin dashboard**: separate React SPA — Vite + TypeScript + Vitest (unit) + Playwright (E2E)
- **AI**: OpenAI API (GPT + Whisper)
- **Storage**: Google Drive / Dropbox (per Shmuel's ask — he wants to see folders directly)
- **Email**: Resend (clean API, generous free tier)
- **Calls**: Twilio (if he wants recording)
- **WhatsApp**: Official Business API via Meta
- **Public site**: WordPress at classicjerusalem.com stays (SEO), pulls listings from the FastAPI backend via API

**Principle**: avoid Docker for local dev unless genuinely necessary. Prefer hosted/managed infra over anything we'd otherwise run ourselves. Pick the best tool per job — this is the default, not a hard rule.

---

## Reference — relevant memory

Project memory saved at:
`/home/matt/.claude/projects/-home-matt-git-shmuelautomation/memory/project_shmuel_realty.md`

---

## Open follow-ups

### Yad2 import — evaluate webot's listing aggregator (Phase 2 trigger)

**Decided 2026-05-05** that Yad2 actively bot-blocks our backend.
ShieldSquare/Datadome serves a captcha to any datacenter IP and even
to residential IPs without proper browser fingerprints. The
`/properties/import/yad2` endpoint already returns a graceful "fill
in manually" warning and the admin UI tells Shmuel that's the norm.

Webot.co.il aggregates Yad2/Madlan/FB/Janglo listings in their real
estate vertical. Shmuel already pays for webot for WhatsApp bulk
sending. **When we kick off webot integration for auto-posting
(Phase 2), also evaluate whether their listing aggregator exposes an
API we can pull from instead of scraping Yad2 directly.** That would
give us structured imports without paying for residential proxies or
maintaining a stealth headless setup.

Trigger to revisit: when starting WhatsApp auto-posting work. Don't
scope it earlier — Yad2 manual entry works fine in the meantime.
