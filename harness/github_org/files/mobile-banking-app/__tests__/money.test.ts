import {formatAmount, signedAmount, spokenAmount} from '../src/utils/money';

describe('money', () => {
  it('formats euro amounts for Ireland', () => {
    expect(formatAmount('12.30', 'EUR', 'en-IE')).toBe('€12.30');
  });

  it('keeps zero-decimal currencies whole', () => {
    expect(formatAmount('1530', 'JPY', 'en-IE')).toBe('JP¥1,530');
  });

  it('shows debits with a minus sign and credits without', () => {
    expect(signedAmount('8.00', 'EUR', false, 'en-IE')).toBe('−€8.00');
    expect(signedAmount('8.00', 'EUR', true, 'en-IE')).toBe('€8.00');
  });

  it('spells the sign out for screen readers', () => {
    expect(spokenAmount('8.00', 'EUR', false, 'en-IE')).toBe('minus €8.00');
  });

  it('falls back to the raw value when the amount is not a number', () => {
    expect(formatAmount('n/a', 'EUR')).toBe('n/a EUR');
  });
});
