# Questions for Shmuel before we can start Phase 3

We've built everything in Phases 1 and 2 that doesn't need decisions
from you. To move into Phase 3 (AI WhatsApp chatbot + automatic
conversation notes in your CRM), we need answers to a few questions.

The detailed engineering plan is in `docs/phase3-roadmap.md`. This
file is the short version, in plain language, to discuss with you.

## What Phase 3 actually gets you

**A WhatsApp chatbot** that answers basic listing questions for you
24/7. Someone messages your WhatsApp at 11pm asking "do you have a
3-bedroom in Talbiya under 12k?" and the bot replies in seconds with
your best 2-3 matches. When the conversation gets serious (showings,
neighborhood questions, anything beyond catalog search), it hands the
thread to you and stops typing. You take over from there.

**Automatic call and WhatsApp summarization.** Every conversation
you have with a lead, owner, or buyer gets summarized into a few
sentences and attached to that person's CRM record. When they call
back two weeks later, you see the prior context immediately instead
of trying to remember.

## What I need to know before building either of these

There are basically three questions.

### 1. Did you sign up for webot yet?

Webot has its own real-estate chatbot product (the "בוט נדל"ן" entry
in their menu). If you sign up for webot for Phase 2 anyway (for the
auto-posting), it might be worth trying their bot product first
before we build our own from scratch.

When you talk to webot, please ask the salesperson three things:

- "Does the real-estate bot accept a property feed from outside, or
  do I have to enter listings into your dashboard?" (We need the
  former so the bot can answer questions about your actual listings,
  not webot's manual entries.)
- "When the bot can't answer something, can it hand off the
  conversation to a human?"
- "What does the bot product cost on top of my regular webot plan?"

If their answers are "yes, yes, reasonable cost," we should try
webot's bot first. If they're "no" to any of the first two, we'll
build our own.

### 2. If we build our own, what phone number does the bot use?

This question only matters if webot's product doesn't fit and we go
the build-our-own route. WhatsApp Business API requires a phone
number that's dedicated to it. The number you currently use for
WhatsApp on your phone can be migrated, but the migration is one-way
and breaks the consumer WhatsApp app on that number (you can't
WhatsApp-message your wife from that number anymore).

Most brokers in your situation either:

- Get a new dedicated number for the bot. Existing contacts keep
  messaging your personal number. New leads message the bot number.
  Costs around USD 5-15/month for the number plus per-conversation
  pricing.
- Keep your personal number for personal contacts, get a separate
  business number for the bot. Same outcome as above; clearer
  separation.

We don't need an answer today. We just need it before we can start
building.

Also, our-side: Meta requires "business verification" before they'll
let you onto the API. That means proving the brokerage is a real
business — a copy of your VAT registration, business license, or
incorporation cert. They typically respond in 1-7 business days. We
can prep the application together; you upload the docs from your
side.

### 3. About the conversation summarization — are you actually opening the CRM?

The "summarize every call and WhatsApp into a CRM note" feature is
only useful if you actually look at the CRM. If your real workflow
is "everything lives in WhatsApp and my phone, I rarely open the
admin," then summarizing into the admin doesn't help you.

Honest answer: how often do you open the admin in a typical week?
Does opening it feel like part of your workflow, or like an extra
step?

If the answer is "rarely," we can build the summarization to email
you a daily digest instead, or to push back into a WhatsApp message
to yourself, so you see it in the place you're already looking. Just
need to know.

## What I'm not asking you to decide today

You don't have to pick Path A vs Path B for the chatbot today. You
don't have to decide on a phone number today. You don't have to
commit to using the CRM differently today.

The decision-tree starts with: are you ready to sign up for webot?
Everything else cascades from that.

## When all this work would actually happen

Once we have your answers, the realistic timeline is:

- 1-3 weeks for the chatbot, depending on which path we pick.
- 1-2 weeks for WhatsApp summarization on top of the chatbot.
- Additional weeks if you want call summarization too (depends on
  how you want to capture call audio).

This is on top of the Phase 2 auto-posting wiring, which is a few
hours of work once webot is set up.
