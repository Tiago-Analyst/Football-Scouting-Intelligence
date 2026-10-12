/**
 * Every sentence the API decides has words on this side, in both languages.
 *
 * The backend used to return finished English prose and this interface printed
 * it. It now sends `{ code, values }` beside that prose, and the code is what
 * the interface renders.
 *
 * The failure this guards against is specific and quiet: somebody adds a code
 * in Python, nothing in TypeScript knows about it, and a reader is shown
 * `role_population_too_small` where a sentence should be. The codes are read
 * out of the Python source rather than listed here, so adding one without
 * words fails the build instead of reaching a page.
 *
 * The second failure it guards against is worse because it looks like success:
 * a Portuguese sentence with an English noun phrase interpolated into it,
 * because the value carried an identifier and nobody translated it.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const BACKEND = fileURLToPath(new URL("../../backend/app/", import.meta.url));
const DICT = fileURLToPath(new URL("../src/i18n/dictionaries/", import.meta.url));
const read = (file) => readFileSync(new URL(`../${file}`, import.meta.url), "utf8");

function messages(locale) {
  return JSON.parse(readFileSync(path.join(DICT, locale, "messages.json"), "utf8"));
}

/** Every `Message(code="…")` the backend can construct. */
function emittedCodes() {
  const found = new Set();
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "__pycache__") continue;
        walk(full);
      } else if (entry.name.endsWith(".py")) {
        const body = readFileSync(full, "utf8");
        // Anchored on the `Message(` constructor and on the analytics
        // layer's `*_reason_code` assignments, and nothing else.
        //
        // Two earlier versions were wrong in opposite directions. The first
        // only understood `code=("a" if … else "b")` and missed six of the
        // seven codes. The second matched any `code=` and swept up HTTP
        // error codes and a `getattr` default - which fails loudly, where
        // the first failed silently and read as a pass.
        for (const at of findAll(body, "Message(")) {
          const call = balanced(body, at + "Message".length);
          const code = /\bcode=([^,)]*)/.exec(call);
          if (code) for (const lit of code[1].matchAll(/"([a-z][a-z_]*)"/g)) found.add(lit[1]);
        }
        // The parenthesised form spans lines, so [\s\S] rather than a
        // line-bounded class - which is what lost two of the seven.
        for (const m of body.matchAll(/_reason_code=\(([\s\S]*?)\)/g)) {
          for (const lit of m[1].matchAll(/"([a-z][a-z_]*)"/g)) found.add(lit[1]);
        }
        for (const m of body.matchAll(/_reason_code="([a-z][a-z_]*)"/g)) found.add(m[1]);
      }
    }
  };
  walk(BACKEND);
  return [...found].sort();
}


/** Every index at which `needle` occurs. */
function findAll(text, needle) {
  const out = [];
  for (let i = text.indexOf(needle); i !== -1; i = text.indexOf(needle, i + 1)) out.push(i);
  return out;
}

/** The parenthesised argument list starting at `from`, balanced. */
function balanced(text, from) {
  const open = text.indexOf("(", from);
  if (open === -1) return "";
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === "(") depth += 1;
    else if (text[i] === ")") {
      depth -= 1;
      if (depth === 0) return text.slice(open, i + 1);
    }
  }
  return text.slice(open);
}

test("the backend emits codes at all", () => {
  // If this finds nothing the rest of the file is vacuous, which is the
  // failure mode a guard like this has.
  const codes = emittedCodes();
  assert.ok(codes.length >= 6, `expected the message codes, found: ${codes.join(", ")}`);
  assert.ok(codes.includes("role_population_too_small"));
  assert.ok(codes.includes("low_evidence_count"));
});

test("every code the backend emits has copy in English", () => {
  const en = messages("en");
  const missing = emittedCodes().filter((code) => !en[code]);
  assert.deepEqual(missing, [], `codes with no English copy: ${missing.join(", ")}`);
});

test("every code the backend emits has copy in Portuguese", () => {
  const pt = messages("pt");
  const missing = emittedCodes().filter((code) => !pt[code]);
  assert.deepEqual(missing, [], `codes with no Portuguese copy: ${missing.join(", ")}`);
});

test("the two languages interpolate the same placeholders", () => {
  const en = messages("en");
  const pt = messages("pt");
  for (const [code, template] of Object.entries(en)) {
    const left = [...template.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
    const right = [...(pt[code] ?? "").matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
    assert.deepEqual(right, left, `${code}: placeholders differ between languages`);
  }
});

test("the identifiers a message carries are translated, not interpolated raw", () => {
  // A Portuguese sentence with an English noun phrase inside it looks like it
  // worked. Every placeholder naming an identifier has a case here.
  const renderer = read("src/components/player/ApiMessage.tsx");
  for (const name of ["role", "noun_key", "dimensions", "metrics", "score"]) {
    assert.match(
      renderer,
      new RegExp(`case "${name}":`),
      `${name} reaches the sentence untranslated`,
    );
  }
});

test("a code with no copy is visible rather than blank", () => {
  const renderer = read("src/components/player/ApiMessage.tsx");
  assert.match(renderer, /if \(!template\) return message\.code;/);
});

test("the English prose is still sent beside the codes", () => {
  // Additive, so anything reading this API today is unaffected. Removing the
  // prose would be a breaking change dressed as a cleanup.
  const schema = readFileSync(path.join(BACKEND, "schemas/api.py"), "utf8");
  for (const [prose, message] of [
    ["role_fit_percentile_reason: str | None", "role_fit_percentile_reason_message"],
    ["unscored_reason: str | None", "unscored_reason_message"],
    ["label: str", "message: Message | None"],
  ]) {
    assert.ok(schema.includes(prose), `${prose} was removed rather than kept`);
    assert.ok(schema.includes(message), `${message} is missing`);
  }
});

test("the message values stay flat and primitive", () => {
  // A nested structure here would be a template language growing inside a
  // schema, and the frontend already has one.
  const schema = readFileSync(path.join(BACKEND, "schemas/api.py"), "utf8");
  assert.match(schema, /values: dict\[str, str \| int \| float\]/);
});

test("the analytical vocabulary a message can name is translated too", () => {
  const glossary = (locale) =>
    JSON.parse(readFileSync(path.join(DICT, locale, "glossary.json"), "utf8"));
  for (const field of ["metrics", "scores", "dimensions", "evidenceNouns"]) {
    const en = Object.keys(glossary("en")[field]).sort();
    const pt = Object.keys(glossary("pt")[field]).sort();
    assert.deepEqual(pt, en, `${field} differs between languages`);
    assert.ok(en.length > 0, `${field} is empty`);
  }
});

test("every configured core dimension has a Portuguese name", () => {
  // The dimensions are football concepts written in player_roles.yaml, and a
  // withheld percentile names the one that was missing.
  const roles = readFileSync(
    fileURLToPath(new URL("../../config/player_roles.yaml", import.meta.url)),
    "utf8",
  );
  const configured = new Set();
  let inDimensions = false;
  for (const line of roles.split("\n")) {
    if (/^ {4}core_dimensions:/.test(line)) {
      inDimensions = true;
      continue;
    }
    if (inDimensions) {
      const match = /^ {6}([a-z][a-z -]*):$/.exec(line);
      if (match) configured.add(match[1]);
      else if (/^ {0,5}\S/.test(line)) inDimensions = false;
    }
  }
  assert.ok(configured.size >= 15, `expected the configured dimensions, found ${configured.size}`);

  const pt = JSON.parse(readFileSync(path.join(DICT, "pt", "glossary.json"), "utf8")).dimensions;
  const missing = [...configured].filter((d) => !pt[d]);
  assert.deepEqual(missing, [], `dimensions with no Portuguese name: ${missing.join(", ")}`);
});

test("every metric the profile can show has a Portuguese name", () => {
  const en = JSON.parse(readFileSync(path.join(DICT, "en", "glossary.json"), "utf8")).metrics;
  const pt = JSON.parse(readFileSync(path.join(DICT, "pt", "glossary.json"), "utf8")).metrics;
  for (const [key, name] of Object.entries(en)) {
    assert.ok(pt[key], `no Portuguese name for ${key}`);
    // xA and npxG are notation and stay as they are; everything else moves.
    if (!/^x[AG]|npxG/.test(name)) {
      assert.notEqual(pt[key], name, `${key} is still English: "${name}"`);
    }
  }
});

test("the extractor finds every code, including the ones it used to miss", () => {
  // Pinned, because this extractor has been wrong twice: once too narrow
  // (five of seven, silently) and once too wide (sweeping up HTTP error
  // codes, loudly). A guard over a guard, which this one has earned.
  const codes = emittedCodes();
  for (const expected of [
    "role_partial_definition",
    "role_definition_unmeasurable",
    "role_population_too_small",
    "no_role_defined_for_position",
    "no_role_reached_coverage",
    "low_evidence_count",
    "evidence_count",
  ]) {
    assert.ok(codes.includes(expected), `the extractor no longer finds ${expected}`);
  }
  // And nothing that is not a message code.
  for (const notACode of ["not_found", "validation_error", "shortlist_error"]) {
    assert.equal(
      codes.includes(notACode),
      false,
      `${notACode} is an HTTP error code, not a message`,
    );
  }
});

test("every configured role caveat is translated", () => {
  // The caveats are prose written in player_roles.yaml, keyed by role. The
  // English in the dictionary is copied from that file, so a caveat edited
  // there and not here would show the old wording in English and nothing at
  // all in Portuguese.
  const roles = readFileSync(
    fileURLToPath(new URL("../../config/player_roles.yaml", import.meta.url)),
    "utf8",
  ).split("\n");

  const configured = new Set();
  let role = null;
  for (const line of roles) {
    if (/^ {2}[a-z_]+:\s*$/.test(line)) role = line.trim().replace(":", "");
    if (line.trim().startsWith("caveat: >-") && role) configured.add(role);
  }
  assert.ok(configured.size >= 10, `expected the configured caveats, found ${configured.size}`);

  for (const locale of ["en", "pt"]) {
    const caveats =
      JSON.parse(readFileSync(path.join(DICT, locale, "glossary.json"), "utf8")).roleCaveats ?? {};
    const missing = [...configured].filter((key) => !caveats[key]);
    assert.deepEqual(missing, [], `${locale} has no caveat for: ${missing.join(", ")}`);
  }
});

test("the Portuguese caveats are not the English ones", () => {
  const en = JSON.parse(readFileSync(path.join(DICT, "en", "glossary.json"), "utf8")).roleCaveats;
  const pt = JSON.parse(readFileSync(path.join(DICT, "pt", "glossary.json"), "utf8")).roleCaveats;
  for (const key of Object.keys(en)) {
    assert.notEqual(pt[key], en[key], `${key} is still English`);
  }
});

test("the similarity meaning is said here, not printed from the API", () => {
  // The API still sends `meaning` as finished English prose, and still should:
  // an existing caller reads it. What it cannot do is reach a Portuguese
  // reader. The sentence is fixed - it states what the index is, with no
  // figure in it - so it belongs in the dictionary rather than in a message
  // code, which is how `profile.roles.meaning` already works.
  for (const page of ["similar/page.tsx", "replacements/page.tsx", "players/[slug]/page.tsx"]) {
    const source = readFileSync(
      fileURLToPath(new URL(`../src/app/[lang]/${page}`, import.meta.url)),
      "utf8",
    );
    const printed = source.match(/\{\s*(?:similar|results)\.meaning\s*\}/);
    assert.equal(printed, null, `${page} prints the API's English meaning`);
  }
});

test("the English meaning in the dictionary is the backend's own sentence", () => {
  // Two copies of one sentence, so they are compared rather than trusted. A
  // reworded constant with a stale dictionary would leave the English reader
  // with yesterday's wording and nobody any the wiser.
  const source = readFileSync(
    fileURLToPath(new URL("../../backend/app/analytics/similarity.py", import.meta.url)),
    "utf8",
  );
  const block = source.slice(source.indexOf("SIMILARITY_MEANING = ("));
  const backend = [...block.slice(0, block.indexOf("\n)")).matchAll(/"([^"]*)"/g)]
    .map((m) => m[1])
    .join("");
  assert.ok(backend.length > 200, "could not read SIMILARITY_MEANING");

  const en = JSON.parse(readFileSync(path.join(DICT, "en", "similarity.json"), "utf8"));
  assert.equal(en.notes.meaning, backend);

  const pt = JSON.parse(readFileSync(path.join(DICT, "pt", "similarity.json"), "utf8"));
  assert.notEqual(pt.notes.meaning, backend, "the Portuguese is still English");
});

test("the English all-leagues constants still say what the dictionary says", () => {
  // Two copies of three strings. The constants are still exported, because
  // the shortlist comparison table renders in the browser and cannot reach a
  // dictionary; the heading on the profile reads the dictionary so a
  // Portuguese reader gets the explanation in Portuguese. Reworded in one
  // place and not the other, the product would describe the same column two
  // ways - which is the exact failure that file's own comment warns about.
  const source = readFileSync(
    fileURLToPath(new URL("../src/components/player/AllLeaguesLabel.tsx", import.meta.url)),
    "utf8",
  );
  const constant = (name) => {
    const at = source.indexOf(`${name} =`);
    assert.notEqual(at, -1, `${name} is gone`);
    return [...source.slice(at, source.indexOf(";", at)).matchAll(/"([^"]*)"/g)]
      .map((m) => m[1])
      .join("");
  };

  const en = JSON.parse(readFileSync(path.join(DICT, "en", "glossary.json"), "utf8")).allLeagues;
  assert.equal(en.label, constant("ALL_LEAGUES_LABEL"));
  assert.equal(en.qualifier, constant("ALL_LEAGUES_QUALIFIER"));
  assert.equal(en.explanation, constant("ALL_LEAGUES_EXPLANATION"));

  const pt = JSON.parse(readFileSync(path.join(DICT, "pt", "glossary.json"), "utf8")).allLeagues;
  for (const key of ["label", "qualifier", "explanation", "tooltipLabel"]) {
    assert.notEqual(pt[key], en[key], `allLeagues.${key} is still English`);
  }
});

test("the replacement meaning is the replacement one, not the similarity one", () => {
  // The two sentences sit in the same shape of callout on two pages, and
  // swapping them is a silent change: the page still reads fluently and says
  // something the product does not mean. So each is checked against the
  // constant it came from.
  const source = readFileSync(
    fileURLToPath(new URL("../../backend/app/api/v1/recruitment.py", import.meta.url)),
    "utf8",
  );
  const block = source.slice(source.indexOf("REPLACEMENT_MEANING = ("));
  const backend = [...block.slice(0, block.indexOf("\n)")).matchAll(/"([^"]*)"/g)]
    .map((m) => m[1])
    .join("");
  assert.ok(backend.length > 100, "could not read REPLACEMENT_MEANING");

  const en = JSON.parse(readFileSync(path.join(DICT, "en", "replacements.json"), "utf8"));
  assert.equal(en.notes.ranksBody, backend);

  const pt = JSON.parse(readFileSync(path.join(DICT, "pt", "replacements.json"), "utf8"));
  assert.notEqual(pt.notes.ranksBody, backend, "the Portuguese is still English");

  // And it is not the other sentence wearing this one's name.
  const similarity = JSON.parse(readFileSync(path.join(DICT, "en", "similarity.json"), "utf8"));
  assert.notEqual(en.notes.ranksBody, similarity.notes.meaning);
});
