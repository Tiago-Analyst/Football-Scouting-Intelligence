import { apiMessage } from "@/i18n/apiMessage";
import { getDictionary } from "@/i18n/dictionaries";
import { formatters } from "@/i18n/format";
import { Card, CardBody } from "@/components/ui/Card";
import type { PlayerDetail } from "@/types/api";

/**
 * Where these numbers come from, and where the player is now.
 *
 * WHAT WENT WRONG WITHOUT THIS
 *
 * The header read
 *
 *     Attacking Midfielder · Brazil · a Danish club · USA MLS · right · 181cm
 *
 * as one line describing one player, and a reader who knows football stops
 * there. A Danish club does not play in MLS. Nothing on the page was wrong:
 * the club came from the market source and is where the player is today, the
 * competition came from the performance source and is where the season below
 * was played, and a summer transfer puts a border between them.
 *
 * The defect was that both were printed as one state under names that did not
 * say which was which. On the served data, 179 of 592 clubs appeared under
 * more than one competition.
 *
 * WHY TWO COLUMNS RATHER THAN A RECONCILIATION
 *
 * There is nothing to reconcile. A player who moved in July has a July club
 * and a May competition and both are current facts about different things.
 * Collapsing them would mean choosing one to discard, and a scout needs both:
 * the competition says what the numbers mean, the club says who to call.
 *
 * `context_note` is the API's sentence for when the two are in different
 * countries - the only comparison the two provider vocabularies support. It
 * is absent on most profiles, which is what makes it worth reading on the
 * ones where it is not.
 */
export async function PlayerContext({ player }: { player: PlayerDetail }) {
  const t = await getDictionary();
  const f = await formatters();
  const copy = t.profile.context;
  const note = apiMessage(t, f, player.context_note);

  return (
    <Card>
      <CardBody>
        <div className="grid gap-6 sm:grid-cols-2">
          <Half
            title={copy.performance}
            hint={copy.performanceHint}
            rows={[
              [copy.competition, player.competition],
              [copy.season, player.season],
              // The club that played the season, and ONLY when it is a
              // different club from the one below.
              //
              // The two names come from different providers and two thirds of
              // the pairs are one club spelled twice - "Once Caldas SA" and
              // "Once Caldas", "Gangwon FC" and "Gangwon Football Club". Two
              // labelled rows would read as a transfer that never happened,
              // which is the defect this card exists to remove rather than
              // one to reproduce inside it.
              //
              // `clubs_agree` is the API's answer, from the comparison
              // identity resolution already uses. Only an explicit `false`
              // shows the row: `null` means the names do not settle it, and
              // claiming a difference on that is more than the data says.
              //
              // Where the season's club is not recorded at all, that is said
              // rather than filled in from the market source - which is what
              // used to happen.
              [
                copy.clubThatSeason,
                player.performance_club == null
                  ? copy.notRecorded
                  : player.clubs_agree === false
                    ? player.performance_club
                    : null,
              ],
              [copy.minutes, player.minutes !== null ? f.count(player.minutes) : null],
            ]}
          />
          <Half
            title={copy.market}
            hint={copy.marketHint}
            rows={[
              [copy.club, player.club],
              [copy.competition, player.current_competition],
            ]}
          />
        </div>
        {note ? (
          <p className="mt-4 border-t border-subtle pt-3 text-xs leading-relaxed text-muted">
            {note}
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}

/** One labelled context. A row with nothing to say is left out, not blanked. */
function Half({
  title,
  hint,
  rows,
}: {
  title: string;
  hint: string;
  rows: [string, string | null | undefined][];
}) {
  const present = rows.filter(([, value]) => value);
  if (!present.length) return null;
  return (
    <section>
      <h2 className="text-xs font-semibold uppercase tracking-wide text-subtle">{title}</h2>
      <p className="mt-0.5 text-[11px] text-subtle">{hint}</p>
      <dl className="mt-2 space-y-1">
        {present.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4 text-sm">
            <dt className="text-muted">{label}</dt>
            <dd className="text-right font-medium">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
