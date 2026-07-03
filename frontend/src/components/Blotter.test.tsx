import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Blotter } from './Blotter';
import { api } from '../api/client';
import type { Order } from '../api/types';

vi.mock('../api/client', () => ({
  api: { stage: vi.fn(), route: vi.fn(), cancel: vi.fn() },
}));

function order(overrides: Partial<Order> = {}): Order {
  return {
    orderRef: 'ref-123',
    cusip: '912828YK0',
    securityDescription: 'US TREASURY 1.5% 2030',
    portfolio: 'PORT-DEMO',
    trader: 'demo',
    side: 'BUY',
    orderType: 'MARKET',
    timeInForce: 'DAY',
    quantity: 1000000,
    limitPrice: null,
    status: 'NEW',
    filledQuantity: 0,
    remainingQuantity: 1000000,
    avgFillPrice: null,
    statusReason: null,
    createdAt: '2026-07-02T14:30:00Z',
    updatedAt: '2026-07-02T14:30:00Z',
    executions: [],
    ...overrides,
  };
}

describe('Blotter', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders an order row with its security', () => {
    render(<Blotter orders={[order()]} onChanged={vi.fn()} />);
    expect(screen.getByText('912828YK0')).toBeInTheDocument();
    expect(screen.getByText('US TREASURY 1.5% 2030')).toBeInTheDocument();
  });

  it('shows the empty state when there are no orders', () => {
    render(<Blotter orders={[]} onChanged={vi.fn()} />);
    expect(screen.getByText(/No orders yet/i)).toBeInTheDocument();
  });

  it('stages a NEW order and refreshes the blotter', async () => {
    const user = userEvent.setup();
    vi.mocked(api.stage).mockResolvedValue(order({ status: 'STAGED' }) as never);
    const onChanged = vi.fn();

    render(<Blotter orders={[order()]} onChanged={onChanged} />);
    await user.click(screen.getByRole('button', { name: /^Stage$/i }));

    expect(api.stage).toHaveBeenCalledWith('ref-123');
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it('offers Route (not Stage) for a STAGED order', () => {
    render(<Blotter orders={[order({ status: 'STAGED' })]} onChanged={vi.fn()} />);
    expect(screen.getByRole('button', { name: /^Route$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Stage$/i })).not.toBeInTheDocument();
  });
});
