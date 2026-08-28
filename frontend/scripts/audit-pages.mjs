/**
 * Audit every route for accessibility and SEO defects that are checkable from
 * the served HTML.
 *
 *   node scripts/audit-pages.mjs                  # against a running dev server
 *   node scripts/audit-pages.mjs --base https://…
 *   node scripts/audit-pages.mjs --strict         # warnings fail too
 *
 * Exit code 1 on any failure.
 *
 * This deliberately checks the *delivered markup*, not the source. A component
 * can look correct and still render without its label, and a heading can be
 * right in JSX and wrong once three components compose. Only what the browser
 * receives is worth asserting.
 *
 * It is not a substitute for axe or a screen reader. It catches the structural
 * mistakes that are unambiguous and easy to reintroduce — a missing h1, a form
 * control with no label, an image with no alt text, a page with no description.
 * Contrast was measured separately when the palette was chosen.
 */

const args = process.argv.slice(2);
const BASE = valueOf("--base") ?? "http://127.0.0.1:3000";
const STRICT = args.includes("--strict");

function valueOf(flag) {
  const index = args.indexOf(flag);
  return index === -1 ? undefined : args[index + 1];
}

/** Every route a visitor can reach. Keep in step with the app directory. */
const ROUTES = [
  "/",
  "/players",
  "/similar",
  "/recruitment",
  "/replacements",
  "/opportunities",
  "/shortlists",
  "/methodology",
  "/data-quality",
  "/status",
  "/about",
  "/sign-in",
  "/register",
];

const FAIL = "fail";
const WARN = "warn";

const findings = [];
const report = (route, severity, check, detail) =>
  findings.push({ route, severity, check, detail });

/** Strip script, style and template content before looking at the markup. */
function strip(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "");
}

function attr(tag, name) {
  const match = tag.match(new RegExp(`${name}\\s*=\\s*"([^"]*)"`, "i"));
  return match ? match[1] : null;
}

function audit(route, html) {
  const body = strip(html);

  // -- Document -----------------------------------------------------------
  const lang = body.match(/<html[^>]*\slang\s*=\s*"([^"]+)"/i);
  if (!lang) {
    report(route, FAIL, "lang", "<html> has no lang attribute; screen readers guess the language");
  }

  const title = body.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  if (!title || !title[1].trim()) {
    report(route, FAIL, "title", "no <title>");
  } else if (title[1].trim().length < 10) {
    report(route, WARN, "title", `title is very short: "${title[1].trim()}"`);
  }

  const description = body.match(/<meta[^>]*name\s*=\s*"description"[^>]*>/i);
  if (!description) {
    report(route, WARN, "description", "no meta description; search results pick their own text");
  }

  // -- Headings -----------------------------------------------------------
  const headings = [...body.matchAll(/<h([1-6])[^>]*>([\s\S]*?)<\/h\1>/gi)].map((m) => ({
    level: Number(m[1]),
    text: m[2].replace(/<[^>]*>/g, "").trim(),
  }));

  const h1s = headings.filter((h) => h.level === 1);
  if (h1s.length === 0) {
    report(route, FAIL, "h1", "no <h1>; the page has no accessible name");
  } else if (h1s.length > 1) {
    report(route, FAIL, "h1", `${h1s.length} <h1> elements: ${h1s.map((h) => h.text).join(", ")}`);
  }

  // A jump from h2 straight to h4 makes a screen reader announce a level that
  // does not exist, and the reader cannot tell what was skipped.
  for (let i = 1; i < headings.length; i += 1) {
    const jump = headings[i].level - headings[i - 1].level;
    if (jump > 1) {
      report(
        route,
        WARN,
        "heading-order",
        `h${headings[i - 1].level} → h${headings[i].level} at "${headings[i].text.slice(0, 40)}"`,
      );
    }
  }

  // -- Landmarks ----------------------------------------------------------
  for (const [element, name] of [
    ["<main", "main"],
    ["<header", "header"],
    ["<footer", "footer"],
  ]) {
    if (!body.toLowerCase().includes(element)) {
      report(route, FAIL, "landmark", `no <${name}>; keyboard users cannot skip to it`);
    }
  }

  // -- Images -------------------------------------------------------------
  for (const tag of body.match(/<img[^>]*>/gi) ?? []) {
    if (attr(tag, "alt") === null) {
      report(route, FAIL, "img-alt", `image with no alt attribute: ${tag.slice(0, 70)}`);
    }
  }

  // -- Form controls ------------------------------------------------------
  // Explicit association: <label for="id">.
  const labelled = new Set(
    [...body.matchAll(/<label[^>]*\sfor\s*=\s*"([^"]+)"/gi)].map((m) => m[1]),
  );

  // Implicit association: <label>Text <input></label>. Equally valid HTML and
  // equally well announced, and the first version of this audit did not know
  // it — reporting eight correctly labelled controls on /recruitment as
  // defects. An audit that cries wolf on correct markup gets ignored, which
  // costs more than the checks are worth.
  const wrappingLabels = [...(body.match(/<label[\s\S]*?<\/label>/gi) ?? [])].filter((block) =>
    block.replace(/<[^>]*>/g, "").trim(),
  );

  const controls = [
    ...(body.match(/<input[^>]*>/gi) ?? []),
    ...(body.match(/<select[^>]*>/gi) ?? []),
    ...(body.match(/<textarea[^>]*>/gi) ?? []),
  ];

  for (const tag of controls) {
    const type = (attr(tag, "type") ?? "").toLowerCase();
    // Hidden inputs and submit buttons carry their own accessible name.
    if (["hidden", "submit", "button", "image"].includes(type)) continue;

    const id = attr(tag, "id");
    const named =
      (id && labelled.has(id)) ||
      attr(tag, "aria-label") !== null ||
      attr(tag, "aria-labelledby") !== null ||
      attr(tag, "title") !== null ||
      wrappingLabels.some((block) => block.includes(tag));

    if (!named) {
      report(
        route,
        FAIL,
        "control-label",
        `form control with no accessible name: ${tag.slice(0, 90)}`,
      );
    }
  }

  // -- Links --------------------------------------------------------------
  for (const anchor of body.match(/<a[^>]*>[\s\S]*?<\/a>/gi) ?? []) {
    const text = anchor.replace(/<[^>]*>/g, "").trim();
    const hasName = text || /aria-label\s*=/i.test(anchor) || /<img[^>]*\salt="[^"]+"/i.test(anchor);
    if (!hasName) {
      report(route, FAIL, "link-name", `link with no text: ${anchor.slice(0, 70)}`);
    }
    if (/target\s*=\s*"_blank"/i.test(anchor) && !/rel\s*=\s*"[^"]*noopener/i.test(anchor)) {
      report(route, FAIL, "link-rel", "target=_blank without rel=noopener");
    }
  }
}

const results = [];
for (const route of ROUTES) {
  const url = `${BASE}${route}`;
  let response;
  try {
    response = await fetch(url, { redirect: "follow" });
  } catch (error) {
    report(route, FAIL, "reachable", `could not fetch: ${error.message}`);
    continue;
  }

  if (!response.ok) {
    report(route, FAIL, "reachable", `HTTP ${response.status}`);
    continue;
  }

  const html = await response.text();
  results.push({ route, bytes: html.length });
  audit(route, html);
}

// ---------------------------------------------------------------------------

const failures = findings.filter((f) => f.severity === FAIL);
const warnings = findings.filter((f) => f.severity === WARN);

console.log(`Audited ${results.length}/${ROUTES.length} routes at ${BASE}\n`);

if (findings.length === 0) {
  console.log("No accessibility or SEO defects found.");
} else {
  const width = Math.max(...findings.map((f) => f.route.length));
  for (const f of findings) {
    const marker = f.severity === FAIL ? "FAIL" : "warn";
    console.log(`${marker}  ${f.route.padEnd(width)}  ${f.check}: ${f.detail}`);
  }
  console.log(`\n${failures.length} failing, ${warnings.length} warning.`);
}

const heaviest = [...results].sort((a, b) => b.bytes - a.bytes).slice(0, 3);
console.log(
  `\nHeaviest documents: ${heaviest.map((r) => `${r.route} ${Math.round(r.bytes / 1024)}KB`).join(", ")}`,
);

process.exit(failures.length > 0 || (STRICT && warnings.length > 0) ? 1 : 0);
