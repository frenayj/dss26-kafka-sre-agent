import {api} from './client';

export interface CardTransaction {
  authId: string;
  merchantName: string;
  amount: string;
  currency: string;
  merchantCountry: string;
  channel: 'CARD_PRESENT' | 'ECOM' | 'RECURRING' | 'MOTO' | string;
  status: 'PENDING' | 'REVERSED' | 'SETTLED';
  authorisedAt: string;
}

export interface TransactionPage {
  items: CardTransaction[];
  /** Cursor for the next page (authorisedAt of the last item), null at the end. */
  nextBefore: string | null;
}

export function fetchTransactions(cardToken: string, before?: string | null): Promise<TransactionPage> {
  const query = before ? `?before=${encodeURIComponent(before)}&limit=50` : '?limit=50';
  return api<TransactionPage>(`/cards/${cardToken}/transactions${query}`);
}

/** Temporary freeze: the only block the customer can lift themselves. */
export function freezeCard(cardToken: string): Promise<void> {
  return api<void>(`/cards/${cardToken}/freeze`, {method: 'POST'});
}

export function unfreezeCard(cardToken: string): Promise<void> {
  return api<void>(`/cards/${cardToken}/freeze`, {method: 'DELETE'});
}

export function reportLostOrStolen(cardToken: string, reason: 'LOST' | 'STOLEN'): Promise<void> {
  return api<void>(`/cards/${cardToken}/block`, {method: 'POST', body: JSON.stringify({reason})});
}
