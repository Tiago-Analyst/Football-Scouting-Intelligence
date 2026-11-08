/**
 * The CSV relay hands over bytes, not a decoded string.
 *
 * WHAT A READER GOT
 *
 * The backend started emitting a UTF-8 BOM on 8 November, so that Excel on
 * Windows would stop falling back to the system code page and mangling
 * accented surnames. Measured on production two hours after that shipped, a
 * downloaded shortlist still began:
 *
 *     22 70 6C   ->   "pl        (i.e. `"player_name`, no BOM)
 *
 * The backend was emitting it. `app/[lang]/shortlists/[id]/export/route.ts`
 * relayed the download with `new Response(await upstream.text(), ...)`, and
 * the fetch specification has `text()` strip a leading byte order mark. The
 * route then re-encoded the string without one.
 *
 * WHY NOTHING FAILED
 *
 * The backend's own test asserts the backend's bytes, which were correct, and
 * passed. There was no test of the relay at all. **A fix that does not reach
 * the reader is worse than an unshipped one, because the suite now claims it
 * works.** That is the gap this file closes.
 *
 * WHAT THESE ASSERT
 *
 * First, the mechanism, demonstrated on the platform's own `Response` so it
 * cannot be argued with. Then that the route uses the one that preserves
 * bytes - which is the thing that will regress if somebody "simplifies" it.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const ROUTE = readFileSync(
  new URL("../src/app/[lang]/shortlists/[id]/export/route.ts", import.meta.url),
  "utf8",
);

const BOM = new Uint8Array([0xef, 0xbb, 0xbf]);
const BODY = new TextEncoder().encode('"player_name"\r\n"Fernández"\r\n');
const WITH_BOM = new Uint8Array([...BOM, ...BODY]);

const firstThree = async (response) =>
  [...new Uint8Array(await response.arrayBuffer())].slice(0, 3);

test("text() strips the mark - the mechanism, not an opinion", async () => {
  // Demonstrated rather than asserted from the specification, so that a
  // future reader does not have to take anybody's word for it.
  const upstream = new Response(WITH_BOM);
  const relayed = new Response(await upstream.text());
  assert.deepEqual(await firstThree(relayed), [0x22, 0x70, 0x6c], "text() kept the BOM");
});

test("arrayBuffer() preserves it", async () => {
  const upstream = new Response(WITH_BOM);
  const relayed = new Response(await upstream.arrayBuffer());
  assert.deepEqual(await firstThree(relayed), [0xef, 0xbb, 0xbf], "the BOM was lost");
});

test("the accented bytes survive either way, which is why this hid", async () => {
  // The content was never wrong. Only the mark that tells Excel how to read
  // it was, which is why the file looked fine everywhere except the one
  // program it is actually opened in.
  const viaText = new Response(await new Response(WITH_BOM).text());
  assert.match(await viaText.text(), /Fernández/);
});

test("the relay does not decode what it relays", () => {
  assert.match(
    ROUTE,
    /new Response\(await upstream\.arrayBuffer\(\)/,
    "the export route decodes the body again",
  );
  const code = ROUTE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.ok(
    !/upstream\.text\(\)/.test(code),
    "the export route is back to text(), which strips the BOM",
  );
});

test("the headers a download needs are still passed through", () => {
  // The fix changed one expression. These are the things beside it that a
  // careless edit could take with it.
  assert.match(ROUTE, /"Content-Type": "text\/csv; charset=utf-8"/);
  assert.match(ROUTE, /upstream\.headers\.get\("content-disposition"\)/);
  assert.match(ROUTE, /"Cache-Control": "no-store, private"/);
});

test("an unauthenticated download is still refused here", () => {
  // Byte handling must not have disturbed the reason this route exists: it
  // relays a session the browser cannot send to the API itself.
  assert.match(ROUTE, /if \(!cookie\)/);
  assert.match(ROUTE, /status: 401/);
});
