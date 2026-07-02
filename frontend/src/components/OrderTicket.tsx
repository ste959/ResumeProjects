import { useMemo, useState } from 'react';
import { api, HttpError } from '../api/client';
import type { OrderSide, OrderType, Security, TimeInForce } from '../api/types';

interface Props {
  securities: Security[];
  portfolio: string;
  onSubmitted: () => void;
}

const SIDES: OrderSide[] = ['BUY', 'SELL'];
const TYPES: OrderType[] = ['MARKET', 'LIMIT'];
const TIFS: TimeInForce[] = ['DAY', 'GTC', 'IOC', 'FOK'];

/** Order-entry ticket: pick a bond, set side/type/qty, submit. Shows validation and
 *  compliance feedback returned by the API. */
export function OrderTicket({ securities, portfolio, onSubmitted }: Props) {
  const [cusip, setCusip] = useState('');
  const [side, setSide] = useState<OrderSide>('BUY');
  const [orderType, setOrderType] = useState<OrderType>('MARKET');
  const [timeInForce, setTimeInForce] = useState<TimeInForce>('DAY');
  const [quantity, setQuantity] = useState('1000000');
  const [limitPrice, setLimitPrice] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [banner, setBanner] = useState<{ kind: 'ok' | 'warn' | 'err'; text: string } | null>(null);

  const selected = useMemo(() => securities.find((s) => s.cusip === cusip), [securities, cusip]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setFieldErrors({});
    setBanner(null);
    try {
      const order = await api.createOrder({
        cusip,
        portfolio,
        trader: 'demo-trader',
        side,
        orderType,
        timeInForce,
        quantity: Number(quantity),
        limitPrice: orderType === 'LIMIT' && limitPrice ? Number(limitPrice) : null,
      });
      // A compliance breach comes back 201 with status REJECTED rather than an error.
      if (order.status === 'REJECTED') {
        setBanner({ kind: 'warn', text: `Rejected by compliance: ${order.statusReason}` });
      } else {
        setBanner({ kind: 'ok', text: `Order ${order.orderRef.slice(0, 8)} staged (${order.status})` });
      }
      onSubmitted();
    } catch (err) {
      if (err instanceof HttpError && err.body?.fieldErrors) {
        setFieldErrors(err.body.fieldErrors);
        setBanner({ kind: 'err', text: 'Please fix the highlighted fields.' });
      } else {
        setBanner({ kind: 'err', text: err instanceof Error ? err.message : 'Submission failed' });
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="ticket" onSubmit={submit}>
      <h2>Order Ticket</h2>

      <label>
        Security
        <select value={cusip} onChange={(e) => setCusip(e.target.value)} required>
          <option value="" disabled>
            Select a bond…
          </option>
          {securities.map((s) => (
            <option key={s.cusip} value={s.cusip}>
              {s.cusip} · {s.description}
              {s.restricted ? '  ⛔' : ''}
            </option>
          ))}
        </select>
      </label>

      {selected && (
        <div className="ticket-ref">
          <span>{selected.rating}</span>
          <span>{selected.sector}</span>
          <span>Px {selected.cleanPrice.toFixed(2)}</span>
          <span className={selected.investmentGrade ? 'ig' : 'hy'}>
            {selected.investmentGrade ? 'IG' : 'HY'}
          </span>
        </div>
      )}

      <div className="row">
        <label>
          Side
          <div className="segmented">
            {SIDES.map((s) => (
              <button
                type="button"
                key={s}
                className={`seg ${side === s ? 'active ' + s.toLowerCase() : ''}`}
                onClick={() => setSide(s)}
              >
                {s}
              </button>
            ))}
          </div>
        </label>
      </div>

      <div className="row">
        <label>
          Type
          <select value={orderType} onChange={(e) => setOrderType(e.target.value as OrderType)}>
            {TYPES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <label>
          TIF
          <select value={timeInForce} onChange={(e) => setTimeInForce(e.target.value as TimeInForce)}>
            {TIFS.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="row">
        <label>
          Quantity (face)
          <input
            type="number"
            value={quantity}
            step={1000}
            min={1000}
            onChange={(e) => setQuantity(e.target.value)}
          />
          {fieldErrors.quantity && <span className="field-err">{fieldErrors.quantity}</span>}
        </label>
        {orderType === 'LIMIT' && (
          <label>
            Limit Price
            <input
              type="number"
              value={limitPrice}
              step={0.01}
              placeholder="e.g. 99.50"
              onChange={(e) => setLimitPrice(e.target.value)}
            />
            {fieldErrors.limitPrice && <span className="field-err">{fieldErrors.limitPrice}</span>}
          </label>
        )}
      </div>

      <button className="submit" type="submit" disabled={submitting || !cusip}>
        {submitting ? 'Submitting…' : `Stage ${side} Order`}
      </button>

      {banner && <div className={`banner ${banner.kind}`}>{banner.text}</div>}
    </form>
  );
}
