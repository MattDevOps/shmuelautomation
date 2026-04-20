# Phase 3 Scope — AI & Client Layer

**Duration**: 4-6 weeks
**Price**: $1,800 (due at phase completion)
**Prerequisite**: Phase 2 complete and signed off
**Status**: draft — revisit before Phase 3 begins (scope may refine based on Phase 1 + 2 learnings)

---

## Goal

Make Classic Jerusalem Realty look 10x more professional than any other broker. Turn conversations into data automatically.

---

## What's IN this phase

### AI chatbot on WhatsApp
- Uses official WhatsApp Business API (legit, no ban risk)
- Client messages your business number: "2 bedroom in Rehavia under 8k"
- Bot replies with matching properties from your database (photo + price + link)
- You can jump into any conversation manually at any time — bot stops when you take over
- All conversations logged to the CRM

### Call + WhatsApp summarization
- Phone calls (if Twilio set up) or WhatsApp conversations auto-summarized
- GPT extracts: client name, contact info, what they're looking for, budget, neighborhood, timeline, key notes
- Structured entry added to CRM automatically
- You review + edit anytime

### Newsletter system
- Signup box on your website ("Subscribe for property updates")
- Subscriber list stored in your database
- Auto-email triggered every N new properties (default: 3, configurable)
- Email shows new listings with photos, price, link to full listing
- Unsubscribe link included (required by law)

### Multi-language site
- AI-translated versions of your site in chosen languages (English, Hebrew, French, Spanish — your pick)
- Translations generated once at build, cached
- Re-translates automatically when content changes
- Language switcher on the site

### Client / CRM view in dashboard
- All clients in one list
- Tagged by what they're looking for
- Full conversation history
- Last contact date, status (hot lead / cold / closed)

---

## What's OUT of this phase

- Multi-tenant / productization (Phase 4, optional, separate pricing)
- Advanced marketing automation (A/B testing emails, etc.)
- Mobile app

---

## Explicit limitations you accept

- **Call recording** requires either Twilio setup OR a call-recording app on your phone. We'll pick during Phase 3 kickoff.
- **AI summaries are drafts** — they'll be 90% correct, but you should review new entries for accuracy.
- **WhatsApp catalog sync** is partial (covered by Business API limitations, not our system).
- **OpenAI costs scale with usage** — see notes.md for cost expectations.

---

## Deliverables at end of Phase 3

- AI chatbot live on your WhatsApp business number
- Call / WhatsApp summarization pipeline running
- CRM view in dashboard with all clients
- Newsletter signup + auto-email system live
- Multi-language site deployed
- Training call on how to use the AI features + CRM

---

## After Phase 3

- Project is complete
- Small fixes and bug patches: handled as a friend, no charge
- Major new features or additions: scoped and priced separately when requested (Phase 4 or later)

---

## Sign-off

- [ ] Shmuel has read and agrees to this scope
- [ ] Matt has read and agrees to this scope
- [ ] Phase 2 complete and paid
- [ ] Phase 3 start date: _____________
