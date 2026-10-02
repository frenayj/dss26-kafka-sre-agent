/** Display helpers. Amounts are decimal strings from the BFF; formatting only, no arithmetic. */
export function formatAmount(amount: string, currency: string, locale: string): string {
  const value = Number(amount);
  if (!Number.isFinite(value)) {
    return `${amount} ${currency}`;
  }
  return new Intl.NumberFormat(locale, {style: 'currency', currency}).format(value);
}

export function formatDateTime(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, {dateStyle: 'medium', timeStyle: 'short'}).format(new Date(iso));
}

/** "2026-08" -> "August 2026" in the user's language. */
export function formatPeriod(period: string, locale: string): string {
  const [year, month] = period.split('-').map(Number);
  return new Intl.DateTimeFormat(locale, {month: 'long', year: 'numeric'}).format(new Date(Date.UTC(year, month - 1, 1)));
}
