// Launching the browser that renders: Google Chrome when it is installed (channel 'chrome'), else the Chromium at
// CHROME_PATH, else Playwright's bundled Chromium (PLAYWRIGHT_BROWSERS_PATH/chromium). The GPU backend follows the
// platform: Metal on macOS, D3D11 on Windows; on Linux the default, with SwiftShader allowed as a fallback (a machine
// without a GPU renders in software: render.ts refuses it unless --allow-software). CHROME_FLAGS adds flags.
import { chromium, type Browser } from 'playwright-core';
import { existsSync } from 'node:fs';
import path from 'node:path';

export function gpuFlags(platform = process.platform): string[] {
  const angle = platform === 'darwin' ? ['--use-angle=metal'] : platform === 'win32' ? ['--use-angle=d3d11'] : ['--enable-unsafe-swiftshader'];
  return [...angle, '--enable-gpu-rasterization', '--ignore-gpu-blocklist'];
}

/** Chromium executables to try after Chrome, in order. */
function fallbacks(): string[] {
  const out: string[] = [];
  if (process.env.CHROME_PATH) out.push(process.env.CHROME_PATH);
  const pw = process.env.PLAYWRIGHT_BROWSERS_PATH;
  if (pw) out.push(path.join(pw, 'chromium'));
  out.push('/opt/pw-browsers/chromium');
  return out.filter((p, i) => out.indexOf(p) === i && existsSync(p));
}

export async function launchBrowser(o: { headless?: boolean; args?: string[] } = {}): Promise<Browser> {
  const args = [...gpuFlags(), ...(o.args ?? []), ...(process.env.CHROME_FLAGS?.split(/\s+/).filter(Boolean) ?? [])];
  const headless = o.headless ?? true;
  if (!process.env.CHROME_PATH) {
    try {
      return await chromium.launch({ channel: 'chrome', headless, args });
    } catch (e) {
      if (!fallbacks().length) throw e;
    }
  }
  const exe = fallbacks()[0];
  if (!exe) throw new Error('no browser to render with: install Google Chrome, or set CHROME_PATH to a Chromium executable');
  return chromium.launch({ executablePath: exe, headless, args });
}
