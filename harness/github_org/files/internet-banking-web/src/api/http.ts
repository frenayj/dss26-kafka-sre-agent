export class HttpError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

/** Same-origin calls to the web BFF; the session cookie is HttpOnly and set by the BFF. */
export async function http<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/web/v1${path}`, {
    credentials: 'same-origin',
    ...init,
    headers: {Accept: 'application/json', 'X-Requested-With': 'fetch', ...init.headers},
  });
  if (res.status === 401) {
    window.location.assign('/login');
  }
  if (!res.ok) {
    throw new HttpError(res.status, `${init.method ?? 'GET'} ${path}: ${res.status}`);
  }
  return (await res.json()) as T;
}

export interface CardTransaction {
  authId: string;
  merchantName: string;
  amount: string;
  currency: string;
  status: 'PENDING' | 'REVERSED' | 'SETTLED';
  authorisedAt: string;
}

export interface TransactionPage {
  items: CardTransaction[];
  nextBefore: string | null;
}

export interface Statement {
  statementId: string;
  statementPeriod: string;
  closingBalance: string;
  currency: string;
  downloadUrl: string;
}

export const fetchTransactions = (cardToken: string, before?: string | null) =>
  http<TransactionPage>(`/cards/${cardToken}/transactions${before ? `?before=${encodeURIComponent(before)}` : ''}`);

export const fetchStatements = (cardToken: string) => http<Statement[]>(`/cards/${cardToken}/statements`);
