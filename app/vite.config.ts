import { defineConfig, normalizePath, type Plugin } from 'vite';
import { cpSync, existsSync } from 'node:fs';
import path from 'node:path';

const repoRoot = path.resolve(import.meta.dirname, '..');
const assetDirs = ['audio', 'data'];
// Blender's EXR plates (blender/render.py) are served in dev, which export renders use, but never copied into a build:
// builds carry the PNG proxies in public/plates/.
const devDirs = [...assetDirs, 'out/plates'];

// Git can check out directory symlinks as plain files on Windows. Serve the
// original assets through Vite and copy them into builds without using symlinks.
function repoAssets(): Plugin {
  return {
    name: 'repo-assets',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        let url: string;
        try {
          url = decodeURI(req.url?.split('?')[0] ?? '');
        } catch {
          return next(); // a malformed URL is Vite's to answer
        }
        const repo = devDirs.some((dir) => url.startsWith(`/${dir}/`));
        // a missing asset or plate frame is a 404, not the SPA fallback's index.html with a 200 (plates.ts falls back
        // from a plate's EXR to its proxy on the error, and a missing track fails with its path, not a JSON parse error)
        if ((repo || url.startsWith('/plates/')) && !existsSync(path.join(repo ? repoRoot : path.join(import.meta.dirname, 'public'), url))) {
          res.statusCode = 404;
          res.end(`not found: ${url}`);
          return;
        }
        if (repo) req.url = `/@fs/${encodeURI(normalizePath(repoRoot))}${req.url}`;
        next();
      });
    },
    writeBundle(options) {
      if (!options.dir) return;
      for (const dir of assetDirs) {
        cpSync(path.join(repoRoot, dir), path.join(options.dir, dir), { recursive: true });
      }
    },
  };
}

export default defineConfig({
  root: '.',
  publicDir: 'public',
  plugins: [repoAssets()],
  // FILM_NO_HMR=1: no live reload (export renders must not reload mid-run when a file changes)
  server: { port: 5173, strictPort: false, hmr: process.env.FILM_NO_HMR ? false : undefined, fs: { allow: [repoRoot] } },
  // one three.js for the app and the examples/jsm modules it imports (EXRLoader, RoomEnvironment)
  resolve: { alias: { '@root': repoRoot }, dedupe: ['three'] },
  build: { target: 'esnext', assetsInlineLimit: 0 },
});
