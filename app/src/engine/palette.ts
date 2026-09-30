import { hexToLinear } from './util';

// GitLoom's tokens (gitloom web/src/styles/tokens.css). The identity is a git diff: blood is the accent and `−`,
// moss is `+` and gain. Blood is never a surface fill, moss never decorates, and only the two of them may bloom.
export const HEX = {
  ink: '#110d10',
  ink2: '#161114',
  panel: '#1e181c',
  panel2: '#282027',
  rule: '#2b2229',
  ruleStrong: '#3e323b',
  bone: '#ede7ea',
  boneDim: '#a99fa5',
  boneFaint: '#6f6469',
  blood: '#c22b45',
  bloodBright: '#dc4a63',
  bloodDim: '#8e1f35',
  moss: '#4aad63',
  mossDim: '#1c3324',
} as const;

export type PaletteKey = keyof typeof HEX;

/** Linear RGB triplets for GL uniforms. */
export const LIN: Record<PaletteKey, [number, number, number]> = Object.fromEntries(
  Object.entries(HEX).map(([k, v]) => [k, hexToLinear(v)]),
) as Record<PaletteKey, [number, number, number]>;

/** CSS rgba() for Canvas2D. */
export function rgba(key: PaletteKey | string, a = 1): string {
  const hex = (HEX as Record<string, string>)[key] ?? key;
  const n = parseInt(hex.replace('#', ''), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
