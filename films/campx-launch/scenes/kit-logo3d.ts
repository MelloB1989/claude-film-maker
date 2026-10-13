// The kit's logo3d as a scene module (its default export), so film.ts can load it lazily: film.ts imports nothing that
// bun's timeline.ts can't resolve.
export { default } from '@kit/3d/logo';
