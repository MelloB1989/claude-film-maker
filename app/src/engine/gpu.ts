// Is WebGL running on the GPU? Under heavy GPU load (a Blender Cycles render beside an export) Chrome can fall back
// to a CPU rasteriser (SwiftShader) without a word, and what it renders is subtly different: another grain hash noise
// and other edges (2-3 levels on average, up to 133 in a still). scripts/render.ts reads the engine's renderer string
// at startup and again at the end of a video, and refuses a software one (--allow-software for a draft).

/** The renderer strings of a CPU rasteriser: Chrome's SwiftShader, Mesa's llvmpipe, Windows' Basic Render Driver, "Software Rasterizer". */
const SOFTWARE_RENDERER = /SwiftShader|llvmpipe|Software|Basic Render|Microsoft Basic/i;

/** Is this unmasked renderer string (see unmaskedRenderer) a CPU rasteriser rather than a GPU? */
export function isSoftwareRenderer(renderer: string): boolean {
  return SOFTWARE_RENDERER.test(renderer);
}

/** What unmaskedRenderer reads of a WebGL context (a WebGL2RenderingContext has all of it). */
export interface RendererSource {
  readonly RENDERER: number;
  isContextLost(): boolean;
  getExtension(name: string): any;
  getParameter(pname: number): any;
}

/**
 * The context's unmasked renderer string, e.g. `ANGLE (Apple, ANGLE Metal Renderer: Apple M5, Unspecified Version)`
 * (WEBGL_debug_renderer_info; the plain RENDERER where Chrome hides that extension). Throws for a lost context, which
 * has none: reading it is also how the end of an export finds that the context went.
 */
export function unmaskedRenderer(gl: RendererSource): string {
  if (gl.isContextLost()) throw new Error('the WebGL context is lost');
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  const name = gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER);
  if (typeof name !== 'string' || !name) throw new Error('the WebGL context reports no renderer string');
  return name;
}
