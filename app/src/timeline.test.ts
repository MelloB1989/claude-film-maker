import { expect, test } from 'bun:test';
import { readdirSync } from 'node:fs';
import path from 'node:path';
import { createServer } from 'vite';

// The scene modules are an import.meta.glob, which only Vite expands (bun has none): transform the modules that glob
// the scenes as the dev server and a build do, and read the list back.
test('the scene module lists hold no test files (a build would bundle bun:test)', async () => {
  const root = path.resolve(import.meta.dir, '..');
  expect(readdirSync(path.join(root, 'src/scenes')).filter((f) => f.includes('.test.')).length).toBeGreaterThan(0);
  const vite = await createServer({
    root, configFile: false, logLevel: 'silent', appType: 'custom',
    server: { middlewareMode: true, hmr: false, ws: false, watch: null, preTransformRequests: false },
    optimizeDeps: { noDiscovery: true, include: [] },
  });
  try {
    for (const m of ['/src/timeline.ts', '/src/main.ts']) {
      const code = (await vite.transformRequest(m))?.code ?? '';
      const scenes = [...code.matchAll(/"(\.\/scenes\/[^"]+)":\s*\(\)\s*=>/g)].map((x) => x[1]!);
      expect(scenes).toContain('./scenes/thread.ts');
      expect(scenes).toContain('./scenes/card.ts');
      expect(scenes.filter((f) => f.includes('.test.'))).toEqual([]);
    }
  } finally {
    await vite.close();
  }
}, 30000);
