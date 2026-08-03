// Negative fixture: ordinary, complete TypeScript. Must produce zero findings.
// Includes shapes that trip naive scanners: the word "eval" inside a longer
// identifier, and a safe DOM write via textContent rather than innerHTML.
//
// This file must not contain placeholder-marker words anywhere, comments included —
// the placeholder rule reads comments on purpose, so a marker here would be a real
// detection, not a false positive.

interface User {
  id: string;
  email: string;
}

export function describeUser(user: User): string {
  return `${user.email} (${user.id})`;
}

export function evaluateTotal(amounts: number[]): number {
  return amounts.reduce((sum, amount) => sum + amount, 0);
}

export function renderSafely(target: HTMLElement, text: string): void {
  target.textContent = text;
}
