/**
 * The header fits the window, so no page scrolls sideways.
 *
 * WHAT A READER GOT
 *
 * Measured in production at a 1024px viewport, on every page in the site,
 * because this is the header:
 *
 *     Portuguese   bar content 1130px, box 1024px   page scrolled 106px
 *     English      bar content 1091px, box 1024px   page scrolled  67px
 *
 * The glyph left the screen on one side and the theme control on the other.
 * Clean at 375, 768 and 1280: the damage sat in the band from 1024 to about
 * 1130, which is where laptops and upright tablets live.
 *
 * The cause was a breakpoint promising room it did not have. The desktop nav
 * switches on at `lg` (1024px) and needs about 1139px of bar beside it, and
 * nothing in the bar was allowed to shrink.
 *
 * THE FIX, AND WHY IT IS THE WORDMARK THAT GOES
 *
 * Hiding the nav instead would cost a reader six links with no sign they
 * exist. The wordmark can go: the glyph stays, it is still the home link, and
 * `SiteHeader` keeps the full name in an `sr-only` span, so nothing is lost
 * to a screen reader. It shows from `sm` to `lg`, stands down across the band
 * the nav needs, and returns at `xl`.
 *
 * WHAT THIS TEST IS, AND IS NOT
 *
 * It is a width budget, not a rendering: there is no browser here. It adds up
 * the bar from the real dictionary strings using per-character constants
 * calibrated against one production measurement, listed under CALIBRATION.
 *
 * That it is only a model is the honest caveat. What earns it a place is that
 * the model reproduces the measurement: it predicts 74px of slack at 1024
 * without the wordmark, and the browser measured the spacer at exactly 74px.
 * It will drift if the font changes, and it is wrong by a couple of percent
 * on the overflowing case. It is here to notice a seventh nav item or a
 * longer language, which is the way this breaks next.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));
const read = (rel) => readFileSync(path.join(SRC, rel), "utf8");
const json = (rel) => JSON.parse(read(rel));

/**
 * CALIBRATION, from the production measurement at 1024px, Portuguese.
 *
 * The bar's children measured: wordmark 240, spacer, nav 600, actions 219.
 *
 *   NAV_CHAR     nav 600 = 65 label characters x C + 6 items x 20 padding
 *                + 5 gaps x 2  ->  C = 7.23
 *   NAME_CHAR    wordmark 240 = glyph 20 + gap 8 + 33 characters x C
 *                ->  C = 6.42. Lower than the nav's because the wordmark is
 *                `tracking-tight`.
 *   ACTIONS      219: account link, locale switcher, theme toggle. Fixed
 *                words in both languages, so it is a constant here.
 */
const NAV_CHAR = 7.23;
const NAME_CHAR = 6.42;
const ITEM_PADDING = 20; // px-2.5 both sides
const ITEM_GAP = 2; // gap-0.5
const GLYPH = 20;
const GLYPH_GAP = 8;
const ACTIONS = 219;
const BAR_GAPS = 3 * 16; // gap-4, between the bar's four children
const BAR_PADDING = 2 * 24; // sm:px-6
const SCROLLBAR = 15;

/** The six links in the header, in both languages. */
const PRIMARY = ["players", "similar", "recruitment", "replacements", "opportunities", "shortlists"];

function navWidth(locale) {
  const items = json(`i18n/dictionaries/${locale}/navigation.json`).items;
  const text = PRIMARY.reduce((sum, key) => sum + items[key].label.length * NAV_CHAR, 0);
  return text + PRIMARY.length * ITEM_PADDING + (PRIMARY.length - 1) * ITEM_GAP;
}

function wordmarkWidth(locale) {
  // The file is the `common` namespace, so `productName` is at its root.
  const name = json(`i18n/dictionaries/${locale}/common.json`).productName;
  return GLYPH + GLYPH_GAP + name.length * NAME_CHAR;
}

/** What the bar needs, with or without the wordmark's text. */
function required(locale, { wordmark }) {
  const logo = wordmark ? wordmarkWidth(locale) : GLYPH;
  return logo + navWidth(locale) + ACTIONS + BAR_GAPS + BAR_PADDING;
}

/** The bar's box at a viewport width. `max-w-7xl` caps it at 1280. */
const box = (viewport) => Math.min(viewport - SCROLLBAR, 1280);

for (const locale of ["pt", "en"]) {
  test(`${locale}: the bar fits at 1024, where the nav switches on`, () => {
    const slack = box(1024) - required(locale, { wordmark: false });
    assert.ok(
      slack >= 40,
      `only ${Math.round(slack)}px of slack at 1024 in ${locale}; the header is about to scroll sideways again`,
    );
  });

  test(`${locale}: the wordmark is why it fits, and would not if it stayed`, () => {
    // The negative control. If this ever passes, the band no longer needs the
    // rule in `Logo` and the rule should go, rather than being kept because
    // it is there.
    const slack = box(1024) - required(locale, { wordmark: true });
    assert.ok(
      slack < 0,
      `the wordmark now fits at 1024 in ${locale} with ${Math.round(slack)}px to spare`,
    );
  });

  test(`${locale}: the bar fits at 1280, where the wordmark comes back`, () => {
    const slack = box(1280) - required(locale, { wordmark: true });
    assert.ok(
      slack >= 60,
      `only ${Math.round(slack)}px of slack at 1280 in ${locale}; the wordmark should return later than xl`,
    );
  });
}

test("the model reproduces the measurement it was calibrated against", () => {
  // Portuguese at 1024 without the wordmark measured 74px of spacer in the
  // browser, against the built app. A model that cannot reproduce its own
  // calibration point is not measuring the thing it claims to.
  const predicted = box(1024) - required("pt", { wordmark: false });
  assert.ok(
    Math.abs(predicted - 74) <= 3,
    `predicts ${Math.round(predicted)}px of slack where the browser measured 74`,
  );
});

test("the wordmark stands down exactly across the band the nav needs", () => {
  const logo = read("components/shell/Logo.tsx");
  const nav = read("components/shell/SiteNav.tsx");

  assert.match(nav, /className="hidden lg:block"/, "the desktop nav no longer switches on at lg");
  assert.match(
    logo,
    /hidden[^"]*\bsm:inline\b[^"]*\blg:hidden\b[^"]*\bxl:inline\b/,
    "the wordmark no longer hides across the lg-to-xl band",
  );
});

test("the rule lives with the thing it governs", () => {
  // It used to be an arbitrary variant in `SiteHeader` reaching into the
  // Logo's last child, so the rule and the reason for it were in different
  // files and neither said what the other was for.
  const header = read("components/shell/SiteHeader.tsx");
  assert.ok(
    !header.includes("span:last-child"),
    "SiteHeader is reaching into the Logo's internals again",
  );
  assert.match(read("components/shell/Logo.tsx"), /sr-only|SiteHeader/, "the Logo no longer explains where the readable name went");
});

test("the full name is still read out where the wordmark is hidden", () => {
  // The whole fix rests on this: the name is not lost, only unprinted.
  const header = read("components/shell/SiteHeader.tsx");
  assert.match(
    header,
    /className="sr-only">\{withProduct\(t, t\.navigation\.home\)\}/,
    "the header no longer names the product for a screen reader",
  );
});
