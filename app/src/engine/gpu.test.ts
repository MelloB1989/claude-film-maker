import { expect, test } from 'bun:test';
import { isSoftwareRenderer, unmaskedRenderer, type RendererSource } from './gpu';

const M5 = 'ANGLE (Apple, ANGLE Metal Renderer: Apple M5, Unspecified Version)';

test("this Mac's GPU passes the hardware check, and so do other GPUs", () => {
  expect(isSoftwareRenderer(M5)).toBe(false);
  for (const gpu of [
    'ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro, Unspecified Version)',
    'ANGLE (NVIDIA, NVIDIA GeForce RTX 4090 Direct3D11 vs_5_0 ps_5_0, D3D11)',
    'ANGLE (AMD, AMD Radeon Pro 5500M OpenGL Engine, OpenGL 4.1)',
    'ANGLE (Intel Inc., Intel(R) Iris(TM) Plus Graphics OpenGL Engine, OpenGL 4.1)',
  ]) expect(isSoftwareRenderer(gpu)).toBe(false);
});

test('SwiftShader, llvmpipe and the other CPU rasterisers fail it', () => {
  for (const cpu of [
    'Google SwiftShader',
    'ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)',
    'llvmpipe (LLVM 15.0.7, 256 bits)',
    'Mesa llvmpipe',
    'ANGLE (Microsoft, Microsoft Basic Render Driver Direct3D11 vs_5_0 ps_5_0, D3D11)',
    'Microsoft Basic Render Driver',
    'Apple Software Renderer',
    'Software Rasterizer',
  ]) expect(isSoftwareRenderer(cpu)).toBe(true);
});

test('the check ignores case', () => {
  expect(isSoftwareRenderer('google swiftshader')).toBe(true);
  expect(isSoftwareRenderer('LLVMPIPE')).toBe(true);
});

/** A WebGL context that answers as Chrome's does: the extension's constant is a token of its own. */
const UNMASKED = 0x9246;
const fakeGL = (o: { lost?: boolean; ext?: boolean; masked?: unknown } = {}): RendererSource => ({
  RENDERER: 0x1f01,
  isContextLost: () => !!o.lost,
  getExtension: (name) => (o.ext !== false && name === 'WEBGL_debug_renderer_info' ? { UNMASKED_RENDERER_WEBGL: UNMASKED } : null),
  getParameter: (p) => (p === UNMASKED ? M5 : p === 0x1f01 ? (o.masked === undefined ? 'WebKit WebGL' : o.masked) : null),
});

test('the unmasked renderer is read from the debug extension, or is the plain one where the extension is hidden', () => {
  expect(unmaskedRenderer(fakeGL())).toBe(M5);
  expect(unmaskedRenderer(fakeGL({ ext: false }))).toBe('WebKit WebGL');
});

test('a lost context has no renderer: reading it throws, and so does a context that answers nothing', () => {
  expect(() => unmaskedRenderer(fakeGL({ lost: true }))).toThrow('lost');
  expect(() => unmaskedRenderer(fakeGL({ ext: false, masked: null }))).toThrow('no renderer');
});
