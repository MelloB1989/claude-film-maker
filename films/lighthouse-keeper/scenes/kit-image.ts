// The kit's Image as a scene module (its default export), so film.ts loads it lazily: film.ts imports nothing that
// bun's timeline.ts can't resolve.
export { default } from '@kit/media/image';
