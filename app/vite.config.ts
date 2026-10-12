import { defineConfig, normalizePath, type Plugin } from 'vite';
import { cpSync, existsSync } from 'node:fs';
import path from 'node:path';

const repoRoot = path.resolve(import.meta.dirname, '..');
// The film a build carries (FILM=<id> bunx vite build); the dev server serves every film (?film=<id>).
const FILM = process.env.FILM || 'showcase';
// served from the repo in dev: every film's folder (data, audio, assets, fonts) and the render output (Blender's plates:
// out/<id>/plates/...), which export renders use, but a build never copies out/
const devDirs = ['films', 'out'];

// Serve the repo's film folders and render output through Vite, and copy the built film's into builds, without symlinks
// (git can check out directory symlinks as plain files on Windows).
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
        // TS modules under films/ are Vite's to transform (film.ts, scenes); everything else there is a file
        if (repo && /\.(ts|tsx|mts)$/.test(url)) return next();
        // a missing asset or plate frame is a 404, not the SPA fallback's index.html with a 200 (plates.ts falls back
        // from a plate's EXR to its proxy on the error, and a missing track fails with its path, not a JSON parse error)
        if (repo && !existsSync(path.join(repoRoot, url))) {
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
      const src = path.join(repoRoot, 'films', FILM);
      // the film's files the page fetches (not its TS: that is bundled)
      for (const dir of ['data', 'audio', 'assets', 'fonts']) {
        if (existsSync(path.join(src, dir))) cpSync(path.join(src, dir), path.join(options.dir, 'films', FILM, dir), { recursive: true });
      }
    },
  };
}

export default defineConfig({
  root: '.',
  publicDir: 'public',
  plugins: [repoAssets()],
  define: { 'import.meta.env.VITE_FILM': JSON.stringify(process.env.FILM ?? '') },
  // FILM_NO_HMR=1: no live reload (export renders must not reload mid-run when a file changes)
  server: { port: 5173, strictPort: false, hmr: process.env.FILM_NO_HMR ? false : undefined, fs: { allow: [repoRoot] } },
  // one three.js for the app and the examples/jsm modules it imports (EXRLoader, RoomEnvironment); films import the
  // engine and the kit as @engine/... and @kit/...
  resolve: {
    alias: { '@root': repoRoot, '@engine': path.join(import.meta.dirname, 'src/engine'), '@kit': path.join(import.meta.dirname, 'src/kit') },
    dedupe: ['three'],
  },
  build: { target: 'esnext', assetsInlineLimit: 0 },
});
