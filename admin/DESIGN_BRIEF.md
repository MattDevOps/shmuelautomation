# Design Brief — Classic Jerusalem Realty Admin

## Aesthetic Direction
**Editorial / documentary, Jerusalem-stone palette.** A printed real-estate prospectus, not a SaaS dashboard.

## Pages

### 1. Site shell (header + nav)
**Now**: brand text + 3 NavLinks in a row.
**After**: A printed-banner-style top with the brand set in the display serif (Sentient, regular, 1.6 rem), a slim tab strip below it for routes, and a thin paper-edge underline. Nav items are uppercase tracked-out small caps in the body sans, with the active tab marked by a 2px clay underline (NOT a left stripe). On wide screens the nav floats right of the brand inline; on narrower viewports it stacks underneath. Background `--paper`, text `--ink`. No shadow, no card.

### 2. PropertiesPage — table view
**This is the daily-driver page; readability beats density.**

- **Page header**: `<h1>` set in Sentient at 1.875 rem, regular weight. To its right, two actions in body sans: "Export to Excel" (ghost) and "New property" (filled in clay, white text).
- **Filters**: a slim horizontal bar of labeled inputs. No card — it sits flat under the header with a single 1px `--edge` divider above and below. Labels are body sans 0.75 rem uppercase tracked-out; controls are 0.875 rem.
- **Table**: a real `<table>` with `border-collapse: collapse`. Row dividers only — no vertical borders, no zebra stripes. Header row is small caps tracked-out. Body row height is 56 px. Hover state: `--paper-deep` background. Status cell uses an inline `<select>` styled as a soft pill (1px edge border, no chevron icon). Price cell uses `font-variant-numeric: tabular-nums` so columns line up. Action cells are right-aligned text links in `--ink-soft`, separated by a paper-thin divider. Table caption (visually hidden but present for a11y).
- **Empty state**: centered display-serif phrase ("No properties match those filters.") in `--ink-soft`, with a subtle "Clear filters" link below if any filters are active.
- **Loading**: skeleton rows (3 of them) in `--paper-deep` — same height as a real row, no spinner.
- **Error**: a paper banner with `--clay` text and a 1px `--clay` border (not `--alert`-colored, since this is an internal admin tool — clay is the warning voice; reserve red for destructive confirmations).

### 3. PropertyEditPage — form + photos
- **Page header**: "Edit property" or "New property" in Sentient. Subhead in body sans `--ink-soft`: the property's neighborhood and short id in edit mode, or a single-line description in create mode.
- **Form**: 2-column grid on desktop, 1-column at < 720 px. Labels above inputs. Body sans 0.75 rem uppercase tracked-out for labels; inputs at 1 rem with 1px `--edge` border, 6 px radius, 12 px padding. Focus: 2px outline in `--clay` (not the input border thickening — that causes layout shift). Hebrew-friendly: `dir="auto"` on `address`, `description`, `notes`, `owner_name`, `neighborhood`. Required fields marked with a single `*` in `--clay` after the label text.
- **Currency / numeric**: tabular-nums.
- **Form actions**: right-aligned, ghost Cancel + filled Save in clay.
- **Photos section**: a horizontal divider (1px `--edge`), then `<h2>` "Photos" in Sentient, then upload control treated as a printed envelope/intake — a `--paper-deep` block with dashed `--edge` border, label "Drop or choose photos", and a hidden `<input type="file">`. Once photos exist, they render as a CSS grid of paper tiles (4:3 ratio), each with a subtle 1px `--edge` border and an action row below the image (text "Open in Drive" link + "Delete" text button). No drop shadows. Drive-not-connected banner uses the clay border + paper-deep fill, with a clear link to Settings.

### 4. ImportYad2Page
- **Page header**: "Import from Yad2" in Sentient. Subhead in body sans: "Paste a Yad2 listing URL — we'll pull what we can. Fill in the rest before saving."
- **URL form**: a single broad input + a clay-filled "Fetch" button, as a horizontal pair.
- **Warnings**: not a yellow box. A small block in `--paper-deep` with a `--clay` headline ("Some details couldn't be extracted") and the warning bullets in `--ink-soft`. Reads more like an editor's note than a system alert.
- **Photos found**: same paper-tile grid as in PropertyEditPage, with caption "Photos found on the listing — you'll re-upload these manually for now."
- **Review and save**: the form below mirrors PropertyEditPage's exact form, but pre-filled.

### 5. SettingsPage
- **Page header**: "Settings" in Sentient.
- **Section header**: "Photo storage" with body-sans helper line.
- **Connection card**: a paper block (1px `--edge`, 16 px radius, 24 px padding). Uses one of two states:
  - **Disconnected**: heading "Google Drive — not connected" in body sans medium. Sub-line in `--ink-soft`. Single primary "Connect Google Drive" button in clay.
  - **Connected**: heading "Connected to Google Drive" in body sans medium with a small `--success` dot to its left. Two definition rows: account email; root folder. Then a ghost "Disconnect" button below.
- **Flash messages** (post-OAuth redirect): a single banner above the section. Success: small `--success` dot + body sans "Google Drive connected." Error: clay text. Both have a "Dismiss" text link.

## Typography Tokens
- `--font-display`: 'Sentient', Georgia, serif
- `--font-body`: 'Switzer', system-ui, -apple-system, sans-serif
- Type scale (rem): 0.75, 0.875, 1, 1.125, 1.25, 1.5, 1.875, 2.5
- Loaded from Fontshare via @import in `index.css` (200kb gzipped, well within budget)

## Motion
- Page transitions: none (admin tool; stay still).
- Button press: `transform: translateY(1px)` on `:active`; no scale animations.
- Input focus: `outline` with `transition: outline-color 120ms ease-out`.
- Photo tile hover: `border-color` deepens to `--ink` over 120ms; image gets a 1.02 scale on `:hover` clipped by overflow.
- Status pill flip: cross-fade the option text only; don't animate the row height.

## Accessibility
- All semantic roles preserved (test suite of 43 depends on them).
- Form `<label>`s wrap or `htmlFor`-link to inputs (already done; preserve).
- Focus outlines visible everywhere — never `outline: none` without an alternative.
- Color contrast checked: clay on paper passes AA at 18px+ (large text); body ink on paper passes AAA.
- `prefers-reduced-motion`: kill the photo-tile scale, keep the focus transition.

## What I'm explicitly NOT doing this pass
- No icon library — it's not needed and adds bytes.
- No drag-and-drop file upload — the native input is fine and more accessible. Visual treatment makes it feel intentional.
- No animation library — CSS transitions are enough.
- No form validation library — current implementation is fine.
- No mobile-first redesign — desktop-primary, tablet-tolerant.
