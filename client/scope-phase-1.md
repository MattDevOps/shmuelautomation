# Phase 1 Scope — Foundation

**Price**: $3,000 (due at phase completion)
**Status**: draft — sign off before work begins

---

## Goal

One clean place for every property. Nothing gets lost. Everything ready to automate in Phase 2.

---

## What's IN this phase

### Property database
- PostgreSQL database storing every property with all fields
- Fields include: type (rent/sale), price, rooms, address/neighborhood, owner name, owner phone, broker fee (yes/no/amount), status (available/rented/sold), photos, notes, date added
- Easy to extend with new fields later without breaking anything

### Admin dashboard
- Web interface where you log in and manage everything
- Upload new property (manual form)
- Edit any property
- Mark available / rented / sold with one click
- Filter and search (by neighborhood, price, type, status)
- View all properties in a table

### Yad2 import
- Paste a Yad2 URL, system pulls what it can (photos, price, rooms, description)
- You review + confirm + add missing info before saving
- If Yad2 blocks us on a specific listing, manual upload path still works

### Photo organization
- Every property's photos auto-uploaded to a dedicated cloud folder (Google Drive or Dropbox — your choice)
- One folder per property, named so you can find them easily
- Photos accessible both through dashboard and directly via your cloud account

### Excel export
- One-click export of all properties into Excel
- Auto-generated daily backup Excel kept in your cloud folder
- Columns: all property fields including owner phone, broker fee status, notes

### WordPress integration
- Your existing site (jerusalem.com) pulls live from the new database
- Visitors see up-to-date listings without you touching WordPress
- Listings on site auto-update when you change something in the dashboard

### Performance cleanup
- Audit current WordPress site, fix biggest speed issues
- Optimize images, caching, and any slow plugins
- Goal: site loads noticeably faster

---

## What's OUT of this phase (Phase 2+ or later)

- Auto-posting to Facebook, WhatsApp, Janglo
- Scheduler (8am/8pm posts, Shabbat rules)
- AI chatbot
- Call summaries
- Newsletter / email marketing
- Multi-language translation
- WhatsApp catalog sync
- CRM / client tracking features
- Design refresh (visual redesign of WordPress) — this phase is performance only

If you want any of these added mid-phase, they become Phase 2+ items. I won't mix them in.

---

## What I need from you before starting

- [ ] WordPress admin login
- [ ] Hosting access (or at minimum, SFTP/FTP credentials)
- [ ] Google Drive or Dropbox account for photos (your choice)
- [ ] Any existing property / client spreadsheets you want imported
- [ ] Confirmation on which of your fields are critical vs nice-to-have (30-min call to review)

---

## Deliverables at end of Phase 1

- Working admin dashboard you can log into from any browser
- Every current property of yours loaded into the new database
- All photos organized in your cloud folder
- WordPress showing listings from the new database
- Daily Excel backup running automatically
- Brief walkthrough / training call so you know how to use it

---

## Sign-off

- [ ] Shmuel has read and agrees to this scope
- [ ] Matt has read and agrees to this scope
- [ ] Start date: _____________
