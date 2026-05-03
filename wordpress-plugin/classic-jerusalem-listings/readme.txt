=== Classic Jerusalem Listings ===
Contributors: classicjerusalem
Tags: real estate, listings, shortcode, jerusalem
Requires at least: 6.0
Tested up to: 6.4
Requires PHP: 7.4
Stable tag: 1.0.0
License: MIT

Pulls property listings from the Classic Jerusalem Realty backend and renders them via a shortcode.

== Description ==

Reads from the public read API at api.classicjerusalem.com (or your own
configured URL) and renders semantic HTML you can style in your theme.

Use the shortcode `[classic_listings]` in any page or post.

Options:

* `type` — `rent` or `sale` (default: both)
* `limit` — number of properties (default: 12)
* `neighborhood` — filter by neighborhood (optional)

Examples:

* `[classic_listings type="rent"]`
* `[classic_listings type="sale" limit="6"]`
* `[classic_listings neighborhood="Baka"]`

Owner phone numbers, broker fee terms, and internal notes are never
exposed by the public API, so they cannot leak to the WordPress site.

Responses are cached for 60 seconds in WordPress transients.

== Installation ==

1. Plugins → Add New → Upload Plugin → choose `classic-jerusalem-listings.zip` → Install Now → Activate.
2. Settings → Classic Listings → set API base URL (or leave blank for production default).
3. Add `[classic_listings]` to any page.

== Changelog ==

= 1.0.0 =
* Initial release: shortcode, settings page, transient cache.
