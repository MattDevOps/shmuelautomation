# Phase 3 roadmap: AI WhatsApp chatbot + conversation summarization

Last updated 2026-05-15.

This is an internal design doc covering the two remaining Phase 3 work
streams. Neither is buildable today; both depend on decisions only
Shmuel can make. The point of this doc is to make those decisions
explicit so we can move when he's ready.

## 1. AI WhatsApp chatbot

### User-visible goal

A lead messages Shmuel's WhatsApp number with something like:

> "Hi, I'm looking for a 3-bedroom in Talbiya under 12k, ideally
> furnished, available from August"

Today: Shmuel reads it on his phone, opens the admin to check what
matches, types back manually. Often the lead waits hours or overnight.

After: the bot reads the message within seconds, parses the criteria
(rooms, neighborhood, max rent, furnished, move-in date), queries
`properties` in Supabase, replies with the 2-3 best matches: name,
price, lead photo, link to the listing page. If the lead asks
anything outside "search the catalog" (e.g. "can I see it tomorrow",
"are pets OK", "what's the neighborhood like"), it pings Shmuel via
push notification or a flagged conversation in the admin and stops
answering for that thread. Shmuel takes over from there.

The win is twofold: (a) cold leads get instant qualification 24/7,
and (b) Shmuel only spends time on serious inquiries.

### Two paths

Both end at the same user experience. They differ in onboarding cost
and where the conversation logic lives.

#### Path A: WhatsApp Cloud API (Meta), we build the bot

The official WhatsApp Business API, formerly only available through
Business Solution Providers (Twilio, MessageBird, 360dialog) and now
also available direct from Meta as "WhatsApp Cloud API". Free tier
allows ~1,000 service conversations/month; service convos in Israel
run roughly USD 0.04-0.08 each beyond that. Marketing-initiated
conversations are more expensive but we don't need them — leads
message us first.

Onboarding (Shmuel-side, sequential, currently estimated several days
to a couple of weeks total):

1. Create a Meta Business account at business.facebook.com linked to
   Shmuel's business identity (the brokerage).
2. Submit business verification: Meta wants a business license,
   incorporation cert, or VAT-registered tax document. They review
   manually. 1-7 business days typical.
3. Add a WhatsApp Business Account (WABA) inside Meta Business
   Manager.
4. Provision a phone number for the WABA. **This is the friction
   point**: moving an existing number that already has consumer
   WhatsApp installed is a one-way migration that kills the consumer
   app on that number. Most brokers in Shmuel's position either:
   (a) get a dedicated number for the bot, accept that consumer
   WhatsApp won't work on it, or (b) use their personal number for
   personal contacts and a second business number for the bot.

Build (our-side, post-onboarding, estimated 1-2 weeks):

1. Webhook endpoint in `backend/`: `POST /webhooks/whatsapp` that
   verifies Meta's HMAC signature, parses inbound messages, dispatches
   to the conversation handler.
2. Conversation handler: state machine per phone number, with a small
   OpenAI gpt-4o-mini call to classify intent (search / question /
   takeover-needed) and extract structured criteria for search.
3. Property matcher: pure SQL against the existing `properties` table
   using extracted criteria. Reuses the same filters the admin already
   has.
4. Reply formatter: shape the matches into a WhatsApp message (text
   body, image attachment for the lead photo, link), call Meta's
   `/messages` endpoint.
5. Takeover signal: when the LLM flags `takeover-needed`, mark the
   thread "human" in a new `whatsapp_threads` table; the bot stops
   replying for that thread until Shmuel "releases" it from the admin.
6. Admin UI: new page showing active threads, recent messages, and a
   "release thread" button.
7. Tests: respx-mocked Meta API + a fake conversation transcript.

Pros: full control of conversation flow, no third-party UX coupling,
cheap at our volume, official ToS path.

Cons: Meta business verification is real friction. Has to be Shmuel's
business identity, not ours. The dedicated-number question is real
and unavoidable.

#### Path B: Webot's "בוט נדל"ן" (real-estate bot) product

Webot.co.il's nav lists a real-estate bot as a product category. We
have not yet probed what the product actually does. It probably
provides a pre-built conversation flow tied to Shmuel's existing
webot WhatsApp number (the one we're already integrating for
auto-posting in Phase 2).

The unknowns are mostly product questions: does it accept a property
feed (so it can answer "do you have X" against our catalog)? Can it
hand off to a human when it gets stuck? Does it support Hebrew +
English? Is there a separate cost on top of webot's standard plan?

These are questions for webot's sales team, not for us. We can't
scope the integration until Shmuel can tell us what their product
actually offers.

Pros: probably much faster to go live (days, not weeks); uses the
same number / account / billing relationship Shmuel will already
have.

Cons: bound to webot's feature set; if they don't accept a property
feed we lose the ability to answer catalog questions; less control
over the conversation tone and takeover semantics.

### Decision criteria

If Shmuel wants the bot to feel custom, integrate deeply with our
property data, and is willing to do Meta verification + provision a
dedicated number: **Path A**.

If Shmuel wants the simplest path to a working bot, doesn't mind
being constrained by webot's product, and is already in the webot
flow for Phase 2: **try Path B first**, evaluate whether it actually
meets the goal, and fall back to Path A if it doesn't.

### What we need from Shmuel

1. Confirmation he has (or is willing to obtain) a Meta Business
   account with business verification documents ready.
2. A clear answer on the bot phone number question: dedicated new
   number, or migrate an existing one knowing the consumer app
   breaks?
3. After he signs up for webot, ask webot's sales reps three
   questions:
   - Does the real-estate bot product accept an external property
     feed (JSON, CSV, REST API) or does it require manual entry?
   - Does it support handing off to a human when the bot gets stuck?
   - What does it cost on top of the base webot plan?

Without answers to these we can't pick a path, and without a path
we can't write code.

## 2. Call and WhatsApp -> CRM summarization

### User-visible goal

Today, Shmuel's call notes and WhatsApp context live in his head and
in his phone's message history. The admin's `property_notes` and
`contact_notes` tables exist but only contain whatever he manually
types in, which is realistically very little.

After: every call he takes (or every WhatsApp thread he has) is
automatically:

1. Transcribed (audio to text for calls, already-text for WhatsApp).
2. Summarized into a structured note: who, what, key numbers, action
   items, follow-up dates.
3. Attached to the right Contact or Property record by phone-number
   match.
4. Surfaced in a daily digest: "yesterday you spoke with 4 contacts;
   here's a one-paragraph summary of each plus 3 action items".

The win: Shmuel's brain stops being the single point of failure for
client context. When a buyer calls back two weeks later, the CRM
already has prior conversation context attached.

### Component breakdown

1. **Call audio capture.** This is the gating component. Options:
   - A recording app on Shmuel's phone (must comply with Israeli
     two-party consent law if calls cross borders, more permissive
     within Israel; he still needs to add a verbal disclosure).
   - Call forwarding via a Twilio number that records, then forwards
     to his cell. Pros: clean signal, programmatic. Cons: callers see
     a different number, Shmuel publishes that number on his
     business cards going forward.
   - VoIP-only setup (he stops taking calls on his cell entirely,
     uses a softphone). Biggest behavior change.
   - Skip calls entirely, only summarize WhatsApp. Most realistic
     starting point.

2. **Transcription.** OpenAI Whisper for audio (Hebrew + English
   both supported well by whisper-large). Pennies per minute. Only
   needed if we do calls.

3. **WhatsApp message ingestion.** Comes for free if Phase 3
   chatbot is shipped (we already see all messages via the
   webhook). Without the chatbot, we'd need either:
   - Periodic export of WhatsApp chat history from Shmuel's phone
     (manual, friction).
   - Webot's `/getContacts` + message history endpoint, if exposed.
   - Skip and only summarize calls.

4. **Summarization + structured extraction.** LLM call (gpt-4o-mini)
   takes a raw conversation and returns JSON: contact_id (resolved
   by phone match), summary paragraph, action items array, mentioned
   dollar amounts, mentioned dates. Easy part.

5. **CRM linking.** Match the conversation's phone number against
   `contacts.phone` and `properties.owner_phone`. Append the
   extracted JSON to a new `conversation_summaries` table with FK
   to whichever record matched. Idempotent on (phone_number,
   conversation_id) so re-processing the same thread doesn't
   duplicate.

6. **Daily digest UI.** New admin page that shows yesterday's
   summaries grouped by contact, plus open action items. Email
   version sent to Shmuel every morning at 08:00 Jerusalem.

### Why this is lowest priority

- It depends on the chatbot infrastructure (Path A or B) to get
  WhatsApp messages flowing without a separate ingestion build.
- The call portion requires a real behavior change from Shmuel.
  Calling a feature successful presumes he'll actually use the new
  setup.
- The value of the feature depends on Shmuel using the CRM daily.
  If his actual workflow is "everything in WhatsApp, never open the
  admin", the summaries can't reach him. Worth confirming with him
  first.

### Phasing if/when we build it

A) WhatsApp-only first, no calls. Build steps 3-6 above on top of
   the Phase 3 chatbot. Two weeks of work. No behavior change for
   Shmuel.
B) Add call summarization later. Pick one of the call-capture options
   above with Shmuel. Steps 1-2 above. Effort depends heavily on the
   capture option.

## Recommendation

Treat (1) chatbot and (2) summarization as a single dependency chain:

- **Today**: paused. Both are blocked on Shmuel.
- **When Shmuel signs up for webot**: start with the Phase 2 auto-poster
  wiring (already scaffolded), and ask webot's sales reps the three
  bot-product questions above. That answer routes us to Path A vs
  Path B for the chatbot.
- **After bot decision**: build whichever path Shmuel picked, plus
  the WhatsApp-only summarization on top.
- **Optionally later**: add call capture + transcription if Shmuel
  is willing to change his calling workflow.

This sequencing means no work gets thrown away. Auto-poster uses
webot. Webot answer routes chatbot path. Chatbot infra carries
WhatsApp summarization for free. Calls bolt on last as a separate
project.
