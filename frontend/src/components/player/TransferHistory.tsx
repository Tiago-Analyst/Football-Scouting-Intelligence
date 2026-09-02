import { Card, CardBody, CardFooter, CardHeader } from "@/components/ui/Card";
import { Table, TableWrap, TBody, TD, TH, THead, TR } from "@/components/ui/Table";
import { formatDate, formatEuro } from "@/lib/format";
import type { Transfer } from "@/types/api";

/**
 * Where a player has been, newest first.
 *
 * The distinction the fee column has to hold: a reported fee of nought is a
 * free transfer, and no reported fee is a fee nobody published. Rendering both
 * as "€0" or both as "–" would collapse two different facts, and a recruitment
 * department reading a loan as a free transfer is exactly the kind of error
 * this project exists to avoid.
 */
export function TransferHistory({ transfers }: { transfers: Transfer[] }) {
  const ordered = [...transfers].sort((a, b) =>
    (b.transfer_date ?? "").localeCompare(a.transfer_date ?? ""),
  );

  return (
    <Card>
      <CardHeader title="Transfer history" description="Newest first." />
      <CardBody className="p-0">
        {ordered.length === 0 ? (
          <p className="px-5 py-4 text-sm text-muted">
            No transfers recorded for this player. The market source does not cover everybody,
            and a player who has not moved has nothing to show either.
          </p>
        ) : (
          <TableWrap className="rounded-none border-0">
            <Table>
              <THead>
                <TR>
                  <TH>Date</TH>
                  <TH>From</TH>
                  <TH>To</TH>
                  <TH>Type</TH>
                  <TH numeric>Fee</TH>
                </TR>
              </THead>
              <TBody>
                {ordered.map((transfer, index) => (
                  <TR key={`${transfer.transfer_date}-${transfer.to_club}-${index}`}>
                    <TD className="whitespace-nowrap">
                      {transfer.transfer_date
                        ? formatDate(transfer.transfer_date)
                        : (transfer.season ?? "–")}
                    </TD>
                    <TD>{transfer.from_club ?? "–"}</TD>
                    <TD className="font-medium">{transfer.to_club ?? "–"}</TD>
                    <TD className="text-muted">{transfer.transfer_type}</TD>
                    <TD numeric>
                      {transfer.fee_eur === null ? (
                        // Not "€0". A fee nobody published and a free transfer
                        // are different facts.
                        <span className="text-subtle" title="No fee was reported">
                          undisclosed
                        </span>
                      ) : transfer.fee_eur === 0 ? (
                        "free"
                      ) : (
                        formatEuro(transfer.fee_eur)
                      )}
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </TableWrap>
        )}
      </CardBody>
      <CardFooter className="text-subtle">
        From the public Transfermarkt dataset. Fees are as reported there, which is not always
        what was paid.
      </CardFooter>
    </Card>
  );
}
