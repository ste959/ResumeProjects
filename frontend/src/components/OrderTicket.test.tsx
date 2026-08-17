import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OrderTicket } from './OrderTicket';
import { api } from '../api/client';
import type { Security } from '../api/types';

// Mock the API client so the ticket is tested in isolation.
vi.mock('../api/client', () => {
  class HttpError extends Error {
    constructor(public status: number, public body: unknown) {
      super('http error');
    }
  }
  return { api: { createOrder: vi.fn() }, HttpError };
});

const securities: Security[] = [
  {
    cusip: '912828YK0',
    isin: 'US912828YK08',
    description: 'US TREASURY 1.5% 2030',
    issuer: 'US TREASURY',
    couponRate: 1.5,
    maturityDate: '2030-08-15',
    faceValue: 1000,
    currency: 'USD',
    sector: 'SOVEREIGN',
    rating: 'AAA',
    investmentGrade: true,
    cleanPrice: 97.82,
    restricted: false,
  },
];

describe('OrderTicket', () => {
  beforeEach(() => vi.clearAllMocks());

  it('submits a valid order and confirms it was staged', async () => {
    const user = userEvent.setup();
    vi.mocked(api.createOrder).mockResolvedValue({
      orderRef: 'abcdef12-3456-7890',
      status: 'NEW',
      statusReason: null,
    } as never);
    const onSubmitted = vi.fn();

    render(<OrderTicket securities={securities} portfolio="PORT-DEMO" canWrite onSubmitted={onSubmitted} />);

    await user.selectOptions(screen.getByLabelText('Security'), '912828YK0');
    await user.click(screen.getByRole('button', { name: /Stage BUY Order/i }));

    expect(api.createOrder).toHaveBeenCalledOnce();
    expect(api.createOrder).toHaveBeenCalledWith(
      expect.objectContaining({ cusip: '912828YK0', side: 'BUY', portfolio: 'PORT-DEMO', orderType: 'MARKET' }),
    );
    expect(onSubmitted).toHaveBeenCalled();
    expect(await screen.findByText(/staged \(NEW\)/i)).toBeInTheDocument();
  });

  it('surfaces a compliance rejection to the trader', async () => {
    const user = userEvent.setup();
    vi.mocked(api.createOrder).mockResolvedValue({
      orderRef: 'x',
      status: 'REJECTED',
      statusReason: 'Security is on the restricted list',
    } as never);

    render(<OrderTicket securities={securities} portfolio="PORT-DEMO" canWrite onSubmitted={vi.fn()} />);

    await user.selectOptions(screen.getByLabelText('Security'), '912828YK0');
    await user.click(screen.getByRole('button', { name: /Stage BUY Order/i }));

    expect(await screen.findByText(/Rejected by compliance/i)).toBeInTheDocument();
    expect(screen.getByText(/restricted list/i)).toBeInTheDocument();
  });

  it('blocks submission for a read-only (signed-out) user', async () => {
    const user = userEvent.setup();
    render(<OrderTicket securities={securities} portfolio="PORT-DEMO" canWrite={false} onSubmitted={vi.fn()} />);

    await user.selectOptions(screen.getByLabelText('Security'), '912828YK0');
    const submit = screen.getByRole('button', { name: /Stage BUY Order/i });
    expect(submit).toBeDisabled();
    expect(screen.getByText(/Sign in as a trader/i)).toBeInTheDocument();

    await user.click(submit);
    expect(api.createOrder).not.toHaveBeenCalled();
  });
});
