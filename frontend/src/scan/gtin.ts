// EAN-8, UPC-A (12) and EAN-13 barcodes: digits plus a GS1 check digit.

export function gtinProblem(value: string): string | null {
  const digits = value.replace(/\s/g, '');
  if (!/^\d+$/.test(digits)) return 'Use digits only.';
  if (![8, 12, 13].includes(digits.length)) return 'A barcode number has 8, 12 or 13 digits.';
  const body = digits.slice(0, -1);
  let sum = 0;
  for (let i = 0; i < body.length; i++) {
    const digit = Number(body[body.length - 1 - i]);
    sum += i % 2 === 0 ? digit * 3 : digit;
  }
  const check = (10 - (sum % 10)) % 10;
  return check === Number(digits.at(-1)) ? null : 'This number fails the barcode check digit. Check it for typos.';
}
