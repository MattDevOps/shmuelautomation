<?php
/**
 * Plugin Name:       Classic Jerusalem Listings
 * Plugin URI:        https://classicjerusalem.com
 * Description:       Pulls property listings from the Classic Jerusalem Realty backend and renders them via a [classic_listings] shortcode.
 * Version:           1.1.0
 * Requires at least: 6.0
 * Requires PHP:      7.4
 * Author:            Classic Jerusalem Realty
 * License:           MIT
 * Text Domain:       classic-jerusalem-listings
 */

if (!defined('ABSPATH')) {
    exit;
}

const CJL_VERSION       = '1.1.0';
const CJL_OPTION_KEY    = 'classic_jerusalem_listings';
const CJL_DEFAULT_API   = 'https://api.classicjerusalem.com';
const CJL_CACHE_SECONDS = 60;

/**
 * Read the saved API base URL, falling back to the production default.
 */
function cjl_api_base()
{
    $opts = get_option(CJL_OPTION_KEY, []);
    $url  = isset($opts['api_base']) ? trim($opts['api_base']) : '';
    return $url !== '' ? rtrim($url, '/') : CJL_DEFAULT_API;
}

/**
 * Fetch a list of public properties. Returns an array of items (possibly
 * empty) or null on hard failure so the shortcode can decide whether to
 * render anything at all.
 *
 * @param array{type?:string,limit?:int,neighborhood?:string} $args
 * @return array|null
 */
function cjl_fetch_listings(array $args)
{
    $params = [];
    if (!empty($args['type']))         $params['type']         = $args['type'];
    if (!empty($args['neighborhood'])) $params['neighborhood'] = $args['neighborhood'];
    if (!empty($args['limit']))        $params['limit']        = (int) $args['limit'];

    $cache_key = 'cjl_' . md5(wp_json_encode($params));
    $cached    = get_transient($cache_key);
    if ($cached !== false) {
        return $cached;
    }

    $url  = cjl_api_base() . '/public/properties?' . http_build_query($params);
    $resp = wp_remote_get($url, ['timeout' => 5]);
    if (is_wp_error($resp) || wp_remote_retrieve_response_code($resp) !== 200) {
        // Cache empty briefly so a hammered page doesn't keep retrying.
        set_transient($cache_key, [], 15);
        return null;
    }

    $body  = json_decode(wp_remote_retrieve_body($resp), true);
    $items = isset($body['items']) && is_array($body['items']) ? $body['items'] : [];
    set_transient($cache_key, $items, CJL_CACHE_SECONDS);
    return $items;
}

/**
 * Render a single property as semantic HTML the theme can style.
 */
function cjl_render_item(array $p)
{
    $hood    = isset($p['neighborhood']) ? esc_html($p['neighborhood']) : '';
    $addr    = isset($p['address'])      ? esc_html($p['address'])      : '';
    $rooms   = isset($p['rooms'])        ? esc_html((string) $p['rooms']) : '';
    $size    = isset($p['size_sqm'])     ? (int) $p['size_sqm']         : 0;
    $type    = isset($p['type'])         ? esc_html($p['type'])         : '';
    $price   = isset($p['price'])        ? number_format((float) $p['price'], 0) : '';
    $curr    = isset($p['currency'])     ? esc_html($p['currency'])     : '';
    $desc    = isset($p['description'])  ? esc_html(wp_trim_words($p['description'], 28)) : '';
    $photos  = isset($p['photos']) && is_array($p['photos']) ? $p['photos'] : [];
    $thumb   = '';
    foreach ($photos as $ph) {
        if (!empty($ph['thumbnail_url'])) {
            $thumb = esc_url($ph['thumbnail_url']);
            break;
        }
    }

    ob_start();
    ?>
    <article class="cjl-listing cjl-listing--<?php echo $type; ?>">
        <?php if ($thumb): ?>
            <div class="cjl-listing__photo">
                <img src="<?php echo $thumb; ?>" alt="" loading="lazy" />
            </div>
        <?php endif; ?>
        <div class="cjl-listing__body">
            <h3 class="cjl-listing__title"><?php echo $hood; ?></h3>
            <?php if ($addr): ?><p class="cjl-listing__address"><?php echo $addr; ?></p><?php endif; ?>
            <p class="cjl-listing__price"><?php echo $curr . ' ' . $price; ?></p>
            <ul class="cjl-listing__meta">
                <?php if ($rooms !== ''): ?><li><?php echo $rooms; ?> rooms</li><?php endif; ?>
                <?php if ($size > 0): ?><li><?php echo $size; ?> m²</li><?php endif; ?>
                <li><?php echo $type === 'rent' ? 'For rent' : 'For sale'; ?></li>
            </ul>
            <?php if ($desc): ?><p class="cjl-listing__desc"><?php echo $desc; ?></p><?php endif; ?>
        </div>
    </article>
    <?php
    return ob_get_clean();
}

/**
 * [classic_listings type="rent" limit="12" neighborhood="Baka"]
 */
function cjl_shortcode($atts)
{
    $atts = shortcode_atts([
        'type'         => '',
        'limit'        => 12,
        'neighborhood' => '',
    ], $atts, 'classic_listings');

    $items = cjl_fetch_listings($atts);
    if ($items === null) {
        return '<p class="cjl-error">Listings are temporarily unavailable. Please refresh in a moment.</p>';
    }
    if (empty($items)) {
        return '<p class="cjl-empty">No listings to show right now.</p>';
    }

    $html = '<div class="cjl-grid">';
    foreach ($items as $p) {
        $html .= cjl_render_item($p);
    }
    $html .= '</div>';
    return $html;
}
add_shortcode('classic_listings', 'cjl_shortcode');

/**
 * Newsletter signup form.
 *
 * [classic_newsletter] renders an HTML form that POSTs to
 * /public/newsletter/subscribe on the same backend the listings shortcode
 * reads from. Submits via fetch() so the page does not reload; on success
 * we swap in a "check your email" message. Falls back to a normal browser
 * submit if JS is disabled.
 *
 * Optional attribute: language="he" defaults the form copy to Hebrew.
 */
function cjl_newsletter_shortcode($atts)
{
    $atts = shortcode_atts([
        'language' => 'en',
    ], $atts, 'classic_newsletter');

    $lang  = $atts['language'] === 'he' ? 'he' : 'en';
    $api   = esc_js(cjl_api_base() . '/public/newsletter/subscribe');
    $form_id = 'cjl-newsletter-' . uniqid();

    if ($lang === 'he') {
        $heading       = 'הצטרפו לרשימת התפוצה';
        $sub_copy      = 'מקבלים מייל על נכסים חדשים בירושלים — בלי ספאם, ניתן להסיר בכל עת.';
        $email_label   = 'דוא"ל';
        $type_label    = 'מתעניינים ב';
        $opt_rent      = 'השכרה';
        $opt_sale      = 'מכירה';
        $opt_both      = 'שניהם';
        $submit_label  = 'הרשמה';
        $thanks        = 'תודה! שלחנו אליך מייל אישור — יש ללחוץ על הקישור כדי להפעיל את ההרשמה.';
        $error         = 'משהו השתבש. נסו שוב מאוחר יותר.';
        $dir           = 'rtl';
    } else {
        $heading       = 'New listings, in your inbox';
        $sub_copy      = 'Get an email when new properties are listed in Jerusalem. No spam, unsubscribe anytime.';
        $email_label   = 'Email';
        $type_label    = "I'm interested in";
        $opt_rent      = 'Rentals';
        $opt_sale      = 'For sale';
        $opt_both      = 'Both';
        $submit_label  = 'Subscribe';
        $thanks        = "Thanks! We've sent a confirmation email — click the link to activate your subscription.";
        $error         = 'Something went wrong. Please try again in a moment.';
        $dir           = 'ltr';
    }

    ob_start();
    ?>
    <form id="<?php echo esc_attr($form_id); ?>" class="cjl-newsletter" dir="<?php echo $dir; ?>" novalidate>
        <h3 class="cjl-newsletter__heading"><?php echo esc_html($heading); ?></h3>
        <p class="cjl-newsletter__sub"><?php echo esc_html($sub_copy); ?></p>
        <label class="cjl-newsletter__field">
            <span><?php echo esc_html($email_label); ?></span>
            <input type="email" name="email" required autocomplete="email" />
        </label>
        <fieldset class="cjl-newsletter__fieldset">
            <legend><?php echo esc_html($type_label); ?></legend>
            <label><input type="radio" name="type_filter" value="both" checked /> <?php echo esc_html($opt_both); ?></label>
            <label><input type="radio" name="type_filter" value="rent" /> <?php echo esc_html($opt_rent); ?></label>
            <label><input type="radio" name="type_filter" value="sale" /> <?php echo esc_html($opt_sale); ?></label>
        </fieldset>
        <input type="hidden" name="language" value="<?php echo esc_attr($lang); ?>" />
        <button type="submit"><?php echo esc_html($submit_label); ?></button>
        <p class="cjl-newsletter__msg" role="status" aria-live="polite"></p>
    </form>
    <script>
    (function(){
        var form = document.getElementById('<?php echo esc_js($form_id); ?>');
        if (!form) return;
        var msg = form.querySelector('.cjl-newsletter__msg');
        var btn = form.querySelector('button');
        form.addEventListener('submit', function(e){
            e.preventDefault();
            msg.textContent = '';
            btn.disabled = true;
            var data = {
                email: form.elements['email'].value.trim(),
                language: form.elements['language'].value,
                type_filter: form.querySelector('input[name="type_filter"]:checked').value,
                source: 'wordpress'
            };
            fetch('<?php echo $api; ?>', {
                method: 'POST',
                headers: {'content-type': 'application/json'},
                body: JSON.stringify(data)
            }).then(function(r){
                if (!r.ok) throw new Error('http ' + r.status);
                form.reset();
                msg.classList.add('cjl-newsletter__msg--ok');
                msg.textContent = <?php echo wp_json_encode($thanks); ?>;
            }).catch(function(){
                msg.classList.add('cjl-newsletter__msg--error');
                msg.textContent = <?php echo wp_json_encode($error); ?>;
            }).finally(function(){
                btn.disabled = false;
            });
        });
    })();
    </script>
    <?php
    return ob_get_clean();
}
add_shortcode('classic_newsletter', 'cjl_newsletter_shortcode');

/**
 * Settings page under Settings → Classic Listings so Shmuel can change
 * the API base URL without editing PHP. Stored in a single option key
 * to keep the database tidy.
 */
function cjl_register_settings()
{
    register_setting('cjl_settings', CJL_OPTION_KEY, [
        'type'              => 'array',
        'sanitize_callback' => 'cjl_sanitize_options',
        'default'           => ['api_base' => CJL_DEFAULT_API],
    ]);

    add_settings_section(
        'cjl_main',
        'Backend connection',
        function () {
            echo '<p>Where the plugin should look for listings. Leave blank to use the production default.</p>';
        },
        'cjl_settings'
    );

    add_settings_field(
        'api_base',
        'API base URL',
        function () {
            $opts  = get_option(CJL_OPTION_KEY, []);
            $value = isset($opts['api_base']) ? esc_attr($opts['api_base']) : '';
            $ph    = esc_attr(CJL_DEFAULT_API);
            echo "<input type=\"url\" name=\"" . CJL_OPTION_KEY . "[api_base]\" value=\"$value\" placeholder=\"$ph\" class=\"regular-text\" />";
            echo '<p class="description">Example: <code>https://api.classicjerusalem.com</code></p>';
        },
        'cjl_settings',
        'cjl_main'
    );
}
add_action('admin_init', 'cjl_register_settings');

function cjl_sanitize_options($input)
{
    $clean = [];
    $clean['api_base'] = isset($input['api_base']) ? esc_url_raw(trim($input['api_base'])) : '';
    return $clean;
}

function cjl_register_admin_page()
{
    add_options_page(
        'Classic Listings',
        'Classic Listings',
        'manage_options',
        'cjl-settings',
        'cjl_render_settings_page'
    );
}
add_action('admin_menu', 'cjl_register_admin_page');

function cjl_render_settings_page()
{
    if (!current_user_can('manage_options')) {
        return;
    }
    ?>
    <div class="wrap">
        <h1>Classic Listings</h1>
        <p>This plugin reads property listings from the Classic Jerusalem Realty backend. Add the shortcode <code>[classic_listings]</code> to any page or post.</p>
        <h2>Shortcode options</h2>
        <ul>
            <li><code>type</code> — <code>rent</code> or <code>sale</code> (default: both)</li>
            <li><code>limit</code> — number of properties to show (default: 12)</li>
            <li><code>neighborhood</code> — filter by neighborhood (optional)</li>
        </ul>
        <p>Examples: <code>[classic_listings type="rent"]</code>, <code>[classic_listings type="sale" limit="6"]</code>, <code>[classic_listings neighborhood="Baka"]</code></p>
        <form action="options.php" method="post">
            <?php
            settings_fields('cjl_settings');
            do_settings_sections('cjl_settings');
            submit_button();
            ?>
        </form>
    </div>
    <?php
}
