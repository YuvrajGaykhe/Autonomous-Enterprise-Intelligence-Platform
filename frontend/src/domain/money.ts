/**
 * Money (spec §7.7; DERIVED from `app/decisions/brief.py` `_money`: "currency, a space, the stated
 * amount comma-grouped, never rounded").
 *
 * Amounts arrive as decimal strings and are formatted by string manipulation only. An amount is
 * never parsed to a float, and amounts in different currencies are never added together.
 */

const DECIMAL = /^(-?)(\d+)(?:\.(\d+))?$/;

/** `5361.44` → `5,361.44`. The stated scale is kept; nothing is rounded. */
export function groupDigits(amount: string): string {
  const match = DECIMAL.exec(amount);
  if (match === null) throw new Error(`not a decimal amount: ${JSON.stringify(amount)}`);
  const [, sign = '', whole = '', fraction] = match;
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return `${sign}${grouped}${fraction === undefined ? '' : `.${fraction}`}`;
}

/** `USD 5,361.44`. */
export function formatMoney(money: { amount: string; currency: string }): string {
  return `${money.currency} ${groupDigits(money.amount)}`;
}

/** Exposure per currency, sorted by currency code, each formatted on its own (no total). */
export function exposureLines(
  exposure: Readonly<Record<string, { amount: string; currency: string }>>,
): string[] {
  return Object.keys(exposure)
    .sort()
    .map((currency) => formatMoney(exposure[currency] as { amount: string; currency: string }));
}
