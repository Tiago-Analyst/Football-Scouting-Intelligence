/**
 * The provider's English country name, in Portuguese.
 *
 * The names come from the platform (`Intl.DisplayNames`); only the provider's
 * own spellings and the four British nations, which have no region code, are
 * listed. A name nobody recognises is shown as it arrived.
 */
const ALIASES: Record<string, string> = {
  "Bosnia-Herzegovina": "BA",
  "Bosnia and Herzegovina": "BA",
  "Chinese Taipei": "TW",
  Congo: "CG",
  "Cote d'Ivoire": "CI",
  "Czech Republic": "CZ",
  Curacao: "CW",
  "DR Congo": "CD",
  Hongkong: "HK",
  "Korea, South": "KR",
  Palestine: "PS",
  "The Gambia": "GM",
  "Trinidad and Tobago": "TT",
  Turkey: "TR",
  Türkiye: "TR",
  USA: "US",
};

const BRITISH: Record<string, string> = {
  England: "Inglaterra",
  "Northern Ireland": "Irlanda do Norte",
  Scotland: "Escócia",
  Wales: "País de Gales",
};

let codes: Map<string, string> | undefined;

function codeFor(name: string): string | undefined {
  if (!codes) {
    codes = new Map();
    const english = new Intl.DisplayNames(["en"], { type: "region", fallback: "none" });
    const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    for (const a of letters) {
      for (const b of letters) {
        const known = english.of(a + b);
        if (known && !codes.has(known)) codes.set(known, a + b);
      }
    }
  }
  return ALIASES[name] ?? codes.get(name);
}

export function nationalityName(name: string, locale: string): string {
  if (!locale.startsWith("pt")) return name;
  if (BRITISH[name]) return BRITISH[name];
  const code = codeFor(name);
  return code ? (new Intl.DisplayNames(["pt-PT"], { type: "region" }).of(code) ?? name) : name;
}
