/**
 * Amount formatting for every screen that shows money. Amounts arrive from
 * the BFF as decimal strings in major units ("12.30"); never parse them into
 * floats for arithmetic, only for display.
 */
export function formatAmount(amount: string, currency: string, locale = 'en-IE'): string {
  const value = Number(amount);
  if (!Number.isFinite(value)) {
    return `${amount} ${currency}`;
  }
  return new Intl.NumberFormat(locale, {style: 'currency', currency}).format(value);
}

/** Debits show with a minus sign, refunds and reversals without. */
export function signedAmount(amount: string, currency: string, isCredit: boolean, locale = 'en-IE'): string {
  const formatted = formatAmount(amount, currency, locale);
  return isCredit ? formatted : `−${formatted}`;
}

/** Accessible label: screen readers read "minus 12 euro 30", not the glyphs. */
export function spokenAmount(amount: string, currency: string, isCredit: boolean, locale = 'en-IE'): string {
  const formatted = formatAmount(amount, currency, locale);
  return isCredit ? formatted : `minus ${formatted}`;
}
