# Classic Jerusalem Realty — Day-to-day Guide

Hi Shmuel — this is the everything-you-need-to-know-to-run-it document.
Read it once end-to-end, then come back to specific sections as needed.

The dashboard lives at **admin.classicjerusalem.com** (or whatever URL
Matt sent you). Open it in any browser. There's no app to install.

> **Where to find this guide later:** bookmark it, or open the dashboard
> and look for "Help" in the corner. If something here is wrong or
> confusing, message Matt — the guide gets updated.

---

## 1. The five-minute orientation

The top of every page has the same navigation bar:

| Tab | What lives here |
|---|---|
| **Properties** | Every listing. The home page. |
| **Queue** | Today's posting schedule — what's due to be posted, when. |
| **Groups** | Your list of WhatsApp groups, Facebook groups, Janglo, etc. |
| **Contacts** | Your address book of buyers, renters, landlords. |
| **Import from Yad2** | Paste a Yad2 link → fill the form for you. |
| **Settings** | Connect Google Drive, configure preferences. |
| **System** | Health check — is everything working? |

You can leave the dashboard open in a browser tab all day. Refreshing
is always safe — nothing is in flight that gets lost.

---

## 2. First-time setup (do this once)

### 2.1 Connect Google Drive

This is how property photos get stored — in **your** Google account, in
folders you can see and access directly.

1. Click **Settings** in the top nav.
2. Find the "Google Drive" section. Click **Connect Google Drive**.
3. Sign in with your Google account when prompted, and click **Allow**.
4. You'll come back to the dashboard. The Settings page now shows
   ✓ "Connected as `your.email@gmail.com`".

That's it. Photos you upload will go into a folder structure like
`Classic Realty / Rent — Baka (4893a584) / photo.jpg`. You can browse
to those folders in your normal Google Drive at any time.

### 2.2 Add your destination groups (the *Groups* page)

Before you can post, the system needs to know **where** you post. This
list usually has 20-30 entries. Adding them all takes ~10 minutes one time.

1. Click **Groups** in the top nav → **New group**.
2. For each group you regularly post to, fill in:
   - **Name** — anything you'll recognize. *"Baka WA — landlords"*, *"Janglo — sales"*, *"WhatsApp Status"*.
   - **Platform** — WhatsApp groups / WhatsApp Status / Facebook / Janglo / Other.
   - **Audience** — *for rent*, *for sale*, or *both*. The share modal will only show this group when posting a matching property.
   - **Link** — paste the URL: a WhatsApp group invite link, a Facebook group URL, your Janglo posting page, etc.
3. Click **Save**.

If you stop using a group, **don't delete it** — just toggle "Active" off.
That way you keep its history, and you can turn it back on later.

### 2.3 Connect contacts (optional but recommended)

If you already have an address book in Excel, Bambi, or Nadlan ONE,
import it now. Section 6.2 below walks through it.

---

## 3. Adding a property

Two paths: type it in yourself, or paste a Yad2 link.

### 3.1 From scratch

1. **Properties → New property**.
2. Fill in **Price** (required) plus whatever else you have. Don't worry
   about getting it perfect — you can edit anytime. The fields:
   - **Type** — rent / sale.
   - **Status** — available / rented / sold. New listings default to *available*.
   - **Rooms / Size / Floor** — keep it simple. Use 3.5 for "3 + dinette," etc.
   - **Neighborhood** + **Address** — important for matching with contacts later.
   - **Owner name + phone** — *internal only.* Never appears on the public site.
   - **Broker fee** — yes / no / partial, plus the amount if relevant.
   - **Description (public)** — what shows on the website. Keep it crisp.
   - **Internal notes** — anything for your eyes only. Won't post anywhere.
3. Click **Create**.

> **Heads up — duplicate detection.** As soon as you've typed a
> neighborhood + address that matches a property you already have,
> a soft warning appears with a link to the existing one. You can
> dismiss it and continue, or open the existing record.

After creating, you land on the property's edit page so you can add
photos right away (next section).

### 3.2 From Yad2

1. **Import from Yad2** in the top nav.
2. Paste the Yad2 URL. Click **Fetch**.
3. The form fills in for you — neighborhood, rooms, size, price, photos.
4. Edit anything that's off, then click **Create**.

If the Yad2 page is unreachable (sometimes their servers are slow),
the form just stays blank and you fall back to the manual path.

### 3.3 Adding photos to a property

1. Open the property's edit page (click **Edit** on its row, or just
   land there after creating).
2. Scroll down to the **Photos** section.
3. Click **Upload photos** → select 1-30 images.
4. They upload to your Google Drive automatically and appear as
   thumbnails. To remove one, click ✕.

Photos sync from Drive every time the page loads — if you delete a
file in Drive directly, it disappears from the dashboard.

---

## 4. The daily posting workflow

This is the part that saves you the most time. The system never
posts on its own — every send is one tap from you, but the *thinking*
is done.

### 4.1 What's due today

Open **Queue** in the top nav. You'll see a list of properties scheduled
for posting today, ordered by priority. Each row shows:

- The property snippet (type, neighborhood, price).
- When it's due (8 AM and 8 PM are the daily slots).
- What action to take.

> Friday afternoon → Saturday night, the queue intentionally pauses.
> No slots, no reminders. Resumes Saturday evening.

### 4.2 Compose & share — the magic button

Tap **Compose & share** on any due property (or open the property's
edit page and tap the same button there).

A modal opens with:

1. **The pre-written post text** — type, neighborhood, price, rooms,
   address, and your description. There's a one-tap toggle between
   **English** and **Hebrew** at the top.
2. **A WhatsApp share button** — opens WhatsApp with the text already
   loaded for direct sharing.
3. **A copy-text button** — copies the post to your clipboard so you
   can paste it anywhere.
4. **A group checklist** — every group from your Groups page that
   matches the property's audience (rent / sale). Each row has:
   - The group name.
   - A small **open ↗** link that takes you straight to that group.
   - A checkbox to tick off as you go.

**Recommended flow** for a property at 8 AM:

1. Compose & share.
2. Pick the language you want for this post.
3. For each group in the checklist:
   - Tap **copy & open ↗** — text is in your clipboard, group is open.
   - Paste, send, come back to the dashboard.
   - Tick the group's checkbox.
4. When all the groups are ticked, tap **Mark slot as posted**. The
   queue advances to the next property.

If you only have time for half the groups, no problem — you can come
back later and finish, then mark posted.

### 4.3 If a slot doesn't apply

- **Skip this slot** — leaves the property in the queue for the next slot.
- **Cancel this slot** — drops it. Comes back on the next normal cycle.

---

## 5. When a property goes off-market

Two ways:

1. **From the Properties list** — change its status dropdown (available
   → rented / sold). Done.
2. **Multi-row** — tick the checkboxes on the rows you want, then use
   the bulk-action bar at the top of the table:
   - **Mark as → rented / sold / available**.
   - **Delete** (asks you to confirm — use this sparingly; status
     changes are usually better than deletes).

When a property leaves "available," the system **automatically cancels
any pending post** for it. You don't have to remember to clean up.

---

## 6. Contacts

Your address book lives under **Contacts**. Each contact has:

- Name, phone, email, language.
- **Segments** — free-form tags. Use them however you want:
  *buyer, renter, landlord, vip, baka, rehavia, looking-3M+*. The
  system uses these to suggest contacts for each property (Section 6.4).

### 6.1 Adding one contact

**Contacts → New contact**. Fill in name (required) + whatever else
you have. Save.

### 6.2 Importing your existing address book

If you have an Excel, Google Sheets, or CSV from another CRM:

1. Make sure it has columns: **Name** (required), and any of **Phone,
   Email, Language, Segments, Notes**. The Segments column should use
   semicolons between tags: `buyer;baka;3M+`.
2. **Contacts → Import CSV** → choose file → **Preview**.
3. The preview shows every row with a colored pill:
   - **WILL CREATE** (green) — new contact.
   - **DUPLICATE — SKIPPED** (gray) — phone already exists.
   - **ERROR — SKIPPED** (red) — missing name, etc.
4. If it looks good, tap **Apply — create N contacts**. The valid
   ones import; everything else is left alone.

Phones are normalized for matching: `+972 50-000-0000` and `+972500000000`
count as the same contact.

### 6.3 Exporting (for webot bulk-send)

**Contacts → Export to webot**. Downloads a CSV with UTF-8 BOM (so
Hebrew renders correctly in Excel and webot). You can filter by segment
first to export only "buyers" or only "Baka renters."

### 6.4 Matching contacts to a property

Open a property's edit page → scroll to **Matching contacts**. The
system shows up to 20 contacts who might be interested, scored by:

- **Audience match** — buyers for sales, renters for rentals.
- **Neighborhood match** — segment matching the property's neighborhood.

Each contact shows their name, phone, and *why* they came up so you
can decide who to reach out to.

---

## 7. The System page

**System** in the top nav is your one-glance health check. It shows:

- Is the database reachable?
- Is Google Drive connected?
- How many posting slots are pending? Any due now?
- How many properties are available?
- How many contacts? How many active groups?

If something's red on this page, that's the first thing to fix. Most
issues are "Drive disconnected — reconnect via Settings" or "no internet."

---

## 8. If something breaks

**Most issues are temporary.** Here's the order to try:

1. **Refresh the page.** 90% of the time this is enough.
2. **Check the System page** — see what's red.
3. **Check your internet.** WhatsApp Web works? Google works? If yes,
   the dashboard should too.
4. **Drive connection lost?** Settings → Reconnect Google Drive. Sign
   in again.
5. **Still stuck? Message Matt.** Include:
   - What you were doing.
   - What you expected to happen.
   - What actually happened (screenshot helps).
   - Time/date so I can find it in the logs.

**You won't lose data** by refreshing or by accidentally clicking the
wrong thing. Properties / contacts / groups can always be edited or
restored from a status change. The only irreversible action is
**Delete**, which always asks "are you sure?" first.

---

## 9. Things the system does NOT do (intentionally)

- **It never posts on its own.** Every send is your tap. This is on
  purpose — automated WhatsApp / Facebook posting can get your number
  banned. The system does the *prep*, you do the *send*.
- **It doesn't store WhatsApp messages or contacts from your phone.**
  Your address book in the dashboard is separate from your phone's.
- **It doesn't share anything publicly that you didn't put in the
  Description field.** Owner phones, broker fee terms, internal notes —
  none of those leave the dashboard.

---

## 10. Quick reference

| If you want to… | Go to… |
|---|---|
| Add a new listing | Properties → New property |
| Import a Yad2 listing | Import from Yad2 |
| Mark a property rented/sold | Properties → status dropdown on the row |
| Mark several at once | Properties → tick checkboxes → bulk bar |
| Post a property to your groups | Queue → Compose & share, OR property edit page → same button |
| Add photos | Property edit page → Photos section |
| Add a contact | Contacts → New contact |
| Bulk-import contacts from Excel | Contacts → Import CSV |
| Export contacts to webot | Contacts → Export to webot |
| Add/edit your group list | Groups |
| See if everything is healthy | System |
| Reconnect Google Drive | Settings |

That's the whole thing. The dashboard is yours — explore it.
