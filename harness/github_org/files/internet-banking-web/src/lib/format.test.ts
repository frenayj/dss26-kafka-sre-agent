import {describe, expect, it} from 'vitest';
import {formatAmount, formatPeriod} from './format';

describe('formatAmount', () => {
  it('uses the locale conventions', () => {
    expect(formatAmount('2045.5', 'EUR', 'en-IE')).toBe('€2,045.50');
    expect(formatAmount('2045.5', 'EUR', 'de-DE')).toBe('2.045,50 €');
  });

  it('falls back to the raw value', () => {
    expect(formatAmount('n/a', 'EUR', 'en-IE')).toBe('n/a EUR');
  });
});

describe('formatPeriod', () => {
  it('names the month in the user language', () => {
    expect(formatPeriod('2026-08', 'en-IE')).toBe('August 2026');
    expect(formatPeriod('2026-08', 'fr-FR')).toBe('août 2026');
  });
});
