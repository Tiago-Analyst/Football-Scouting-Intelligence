# Glossary: English to European Portuguese

The single source of football and analytical terminology for this product. No
component invents a translation; every Portuguese term a reader sees comes from
the dictionaries built on this table.

**European Portuguese only.** Brazilian forms are wrong here, and a test
refuses a list of them outright — see `frontend/tests/i18n-glossary.test.mjs`.

---

## The product rule for role names

**Portuguese is the interface language. The English name appears only where it
earns its place as terminology mapping, and never on a dense surface.**

These fifteen role names are this product's own coinages rather than standard
football vocabulary, so a scout does need to be able to connect "Organizador
recuado" to the role as documented and as discussed with an analyst working in
English. But showing the English everywhere pays that cost on every row of
every table, and the result reads as an English product with Portuguese labels
stuck on it. It should read as a Portuguese product.

So the surface decides, and there are exactly two kinds:

| Surface | Shows |
|---|---|
| **Prominent** — profile role header, role breakdown, recruitment preset detail, methodology, glossary, help text | Portuguese, with the English beneath it |
| **Dense** — tables, filters, compact cards, mobile result lists | Portuguese alone |

In code this is one component with one prop, `RoleName`, and `context` is
either `"prominent"` or `"dense"`. No component chooses a role's words for
itself and nothing interpolates a role name by hand: a test asserts that the
only place a role is named is the glossary dictionary.

Where the English is useful on a dense surface, it belongs in a tooltip or in
the methodology, not in the row.

In English, `context` changes nothing: the name is the name.

Rejected alternatives: English beside every occurrence (noise, and the reading
above), Portuguese alone everywhere (loses the mapping exactly where a reader
is studying one role closely), and per-role judgement (produces the
inconsistency a glossary exists to stop).

---

## Roles

| English | Português (PT) | Notes |
|---|---|---|
| Ball-Playing Centre-Back | **Defesa-central construtor** | "Construtor" carries the first-phase build-up meaning that "que sai a jogar" says longer. |
| Defensive Stopper | **Central de marcação** | The role weights duels, blocks and clearances. "Stopper" has no Portuguese equivalent; "de marcação" names what it measures. "Central" rather than "defesa-central" because that is how the position is spoken about in Portugal, and the longer form reads like a dictionary entry in a column heading. |
| Defensive Full-Back | **Lateral defensivo** | |
| Attacking Full-Back | **Lateral ofensivo** | Not "atacante", which in Portugal names a forward. |
| Ball-Winning Midfielder | **Médio recuperador** | "Trinco" is the common spoken term but implies a fixed holding position; the role is about recovery, not position. |
| Deep-Lying Playmaker | **Organizador recuado** | |
| Box-to-Box Midfielder | **Médio box-to-box** | Kept in English inside the Portuguese term: it is what the position is called in Portuguese football. Translating it ("médio de ligação") names a different role. |
| Advanced Playmaker | **Organizador avançado** | |
| Creative Winger | **Extremo criativo** | |
| Direct Winger | **Extremo driblador** | The role is "a wide player who attacks the defender" — dribbles and fouls drawn. "Directo" would be a false friend. The English name in `config/player_roles.yaml` is **Direct Winger** and is unchanged; the Portuguese reads as "dribbling winger" because that is what the role measures. |
| Inside Forward | **Avançado interior** | A wide player who scores rather than supplies. |
| Poacher | **Avançado de área** | "Oportunista" suggests luck. "Finalizador de área" was rejected on review: it names an attribute a player has, where every other entry in this table names a role a player occupies. |
| Target Forward | **Avançado de referência** | The standard Portuguese term for the role. |
| Complete Forward | **Avançado completo** | |
| Shot Stopper | **Guarda-redes de linha** | "Guarda-redes" never "goleiro". "De linha" marks shot-stopping as against sweeping or distribution. |

## Positions

| English | Português (PT) |
|---|---|
| Goalkeeper | **Guarda-redes** |
| Centre-Back | **Defesa-central** |
| Full-Back / Wing-Back | **Lateral** |
| Defensive Midfield | **Médio defensivo** |
| Central Midfield | **Médio centro** |
| Attacking Midfield | **Médio ofensivo** |
| Winger | **Extremo** |
| Centre-Forward | **Avançado** |

## Analytical concepts

| English | Português (PT) | Notes |
|---|---|---|
| Raw Role Fit | **Aptidão bruta para o papel** | "Bruta" marks it as the unranked composite. Never "cru". |
| Role Fit Percentile | **Percentil de aptidão para o papel** | |
| Metric Coverage | **Cobertura de métricas** | How much of a role definition could be measured. |
| Analytical Metric Coverage | **Cobertura analítica de métricas** | |
| Feature Coverage | **Cobertura de atributos** | Deliberately a different word from métricas: the product keeps these two ideas apart, and so must the translation. |
| Similarity Index | **Índice de semelhança** | An index, not a percentage — the copy says so in both languages. |
| Evidence-aware ranking | **Ordenação ponderada pela evidência** | |
| Sample Band | **Escalão de amostra** | |
| Very Low Sample | **Amostra muito reduzida** | |
| Low Sample | **Amostra reduzida** | |
| Developing Sample | **Amostra em formação** | Describes the season, not the player. |
| Established Sample | **Amostra consolidada** | |
| Partial Role Evidence | **Evidência parcial do papel** | |
| Full Role Fit | **Aptidão completa para o papel** | |
| Unavailable | **Indisponível** | Never "não disponível" in a badge: it must stay short. |
| All-Leagues Percentile | **Percentil de todas as ligas** | |
| Mixed Season Maturity | **Épocas em fases diferentes** | A literal "maturidade de época mista" says nothing in Portuguese. This names the actual fact: the competitions are at different points in their seasons. |
| Excellent / Good / Partial / Limited coverage | **Cobertura excelente / boa / parcial / limitada** | |
| Minutes played | **Minutos jogados** | |
| Recorded minutes | **Minutos registados** | |
| Season | **Época** | Never "temporada". |
| Match | **Jogo** | |
| Squad | **Plantel** | |
| Contract expires | **Fim de contrato** | The event. |
| Contract until | **Contrato até** | The profile card's label, which is followed by a date. "Fim de contrato até Dez 2027" would say the same thing twice. |
| Market value | **Valor de mercado** | Always paired with the existing caveat that it is an estimate, not a fee. |
| Shortlist | **Lista de candidatos** | |
| Replacement | **Substituto** | |
| Opportunity | **Oportunidade** | |

## Kept in English on purpose

| Term | Why |
|---|---|
| xG, npxG, xA | Standard notation in Portuguese football analysis. Translating them would make the figures unreadable to the people who use them. |
| per 90 / /90 | Written **/90** in both languages, as it already is. |
| Box-to-box | Inside the role name only; see above. |
| FootyStats, Transfermarkt | Product and dataset names. |
| Canonical metric keys (`npxg_per90`, …) | Identifiers, not copy. They appear in Data Quality and System Status as the provider's own field names and must match the provider and the configuration exactly. |
| Role identifiers (`deep_lying_playmaker`, …) | Same reason: they are keys shared with `config/player_roles.yaml` and the API. |

## Brazilian forms this product does not use

Checked by test, not by intention alone.

| Not this | This |
|---|---|
| goleiro | guarda-redes |
| zagueiro | defesa-central |
| volante | médio defensivo |
| meia / meio-campista | médio |
| atacante | avançado |
| ponta / ponta-de-lança | extremo / avançado |
| lateral-direito (as "lateral direito") | lateral direito |
| temporada | época |
| time | equipa |
| técnico | treinador |
| craque | — (not used) |
| chute | remate |
| gol | golo |
| escanteio | canto |
| cartão | cartão (same) |
| usuário | utilizador |
| tela | ecrã |
| arquivo | ficheiro |
| planilha | folha de cálculo |
| aplicativo | aplicação |
| gerenciar | gerir |
| cadastro | registo |
| senha | palavra-passe |

## Register

Professional, analytical, concise — the Portuguese of a scouting department,
not of a newspaper match report. The English copy argues with the reader about
what a number does and does not mean; the Portuguese does the same, at the same
length. Shortening an argument in translation changes the product.

Second person is avoided in both languages, as the English already does
("Set the criteria", not "You set the criteria"). Where direct address is
unavoidable the Portuguese uses the infinitive or the impersonal, never
"você".
