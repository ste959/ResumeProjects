import type { Position } from '../api/types';
import { fmtMoney, fmtPrice, fmtQty } from '../util/format';

/** Portfolio holdings with live mark-to-market, updated as fills arrive. */
export function Positions({ positions }: { positions: Position[] }) {
  const totalMv = positions.reduce((sum, p) => sum + p.marketValue, 0);

  return (
    <div className="panel positions">
      <div className="panel-head">
        <h2>Positions</h2>
        <span className="count">{fmtMoney(totalMv)} MV</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Security</th>
              <th className="num">Net Qty</th>
              <th className="num">Avg Cost</th>
              <th className="num">Mark</th>
              <th className="num">Market Value</th>
            </tr>
          </thead>
          <tbody>
            {positions.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  No positions yet — fills will build the book.
                </td>
              </tr>
            )}
            {positions.map((p) => (
              <tr key={p.cusip}>
                <td>
                  <div className="sec">{p.cusip}</div>
                  <div className="sec-desc">{p.securityDescription}</div>
                </td>
                <td className={`num mono ${p.netQuantity < 0 ? 'sell' : 'buy'}`}>{fmtQty(p.netQuantity)}</td>
                <td className="num mono">{fmtPrice(p.avgCost)}</td>
                <td className="num mono">{fmtPrice(p.markPrice)}</td>
                <td className="num mono">{fmtMoney(p.marketValue)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
