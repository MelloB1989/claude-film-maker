// The palette: colours by role (docs/CONVENTIONS.md), never by hue, so every scene, kit block and shader follows the
// film's theme. A theme is a preset from themes.json or a preset with overrides; setTheme() switches it before anything
// is built (Engine.init does, from the film's `theme`). HEX and LIN are live: setTheme updates them in place, so code
// that reads HEX.accent or LIN.fg when it draws or builds a material sees the film's colours. Shaders bake the palette
// as GLSL constants (glsl/common.ts glslCommon) when they compile, which is after setTheme.
import PRESETS from './themes.json';
import { hexToLinear } from './util';

/** Every colour role a theme defines. */
export const ROLES = [
  'bg', 'bg2', 'surface', 'surface2', 'rule', 'ruleStrong',
  'fg', 'fgDim', 'fgFaint',
  'accent', 'accentBright', 'accentDim',
  'accent2', 'accent2Bright', 'accent2Dim',
] as const;

export type PaletteKey = (typeof ROLES)[number];
export type Palette = Record<PaletteKey, string>;
/** A resolved theme: its colours, whether its background is dark or light, and its name. */
export interface Theme extends Palette {
  name: string;
  kind: 'dark' | 'light';
}
/** A preset's name, or a preset (default `noir`) with some of its roles (and its kind) overridden. */
export type ThemeSpec = string | ({ extends?: string; kind?: 'dark' | 'light' } & Partial<Palette>);

/** The built-in presets (themes.json): noir, midnight, ember, aurora, mono, paper. */
export const THEME_PRESETS = PRESETS as Record<string, Palette & { kind: 'dark' | 'light' }>;
export const DEFAULT_THEME = 'noir';

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

/** A theme spec resolved against the presets; throws on an unknown preset, a missing role or a malformed colour. */
export function resolveTheme(spec: ThemeSpec = DEFAULT_THEME): Theme {
  const o = typeof spec === 'string' ? { extends: spec } : spec;
  const name = o.extends ?? DEFAULT_THEME;
  const base = THEME_PRESETS[name];
  if (!base) throw new Error(`unknown theme '${name}' (presets: ${Object.keys(THEME_PRESETS).join(', ')})`);
  const t = { ...base, ...o, name: typeof spec === 'string' ? spec : `${name}*` } as Theme & { extends?: string };
  delete t.extends;
  for (const k of ROLES) if (!HEX_RE.test(t[k])) throw new Error(`theme ${t.name}: ${k} must be a #rrggbb colour, got '${t[k]}'`);
  if (t.kind !== 'dark' && t.kind !== 'light') throw new Error(`theme ${t.name}: kind is 'dark' or 'light'`);
  return t;
}

/** The current theme (live). */
export let THEME: Theme = resolveTheme();
/** The current theme's colours as hex (live: setTheme updates this object in place). */
export const HEX: Palette = { ...THEME };
/** Linear RGB triplets for GL uniforms (live). */
export const LIN = {} as Record<PaletteKey, [number, number, number]>;
/** Bumped by every setTheme: caches of anything built from the palette key on it. */
export let themeVersion = 0;

function apply(t: Theme) {
  THEME = t;
  for (const k of ROLES) {
    HEX[k] = t[k];
    LIN[k] = hexToLinear(t[k]);
  }
  themeVersion++;
}
apply(THEME);

/** Switch the theme. Call it before scenes build their materials and shaders compile (Engine.init does). */
export function setTheme(spec: ThemeSpec): Theme {
  apply(resolveTheme(spec));
  return THEME;
}

/** CSS rgba() for Canvas2D: a palette role or any #rrggbb. */
export function rgba(key: PaletteKey | string, a = 1): string {
  const hex = (HEX as Record<string, string>)[key] ?? key;
  const n = parseInt(hex.replace('#', ''), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

/** Linear RGB of a role or a #rrggbb. */
export function lin(key: PaletteKey | string): [number, number, number] {
  return (LIN as Record<string, [number, number, number]>)[key] ?? hexToLinear(key);
}

/** Linear-light mix of two roles (or colours), 0 → a, 1 → b. */
export function mixLin(a: PaletteKey | string, b: PaletteKey | string, k: number): [number, number, number] {
  const x = lin(a), y = lin(b);
  return [x[0] + (y[0] - x[0]) * k, x[1] + (y[1] - x[1]) * k, x[2] + (y[2] - x[2]) * k];
}
