// The starter film: copy this folder to films/<your-id>/, set the id in film.json, and build from here.
import { defineFilm } from '@engine/film';
import config from './film.json';

export default defineFilm({
  ...config,
  scenes: [
    { id: 'hello', scene: () => import('./scenes/hello'), length: { bars: 2 }, params: { title: 'Hello, film.' } },
    { id: 'world', scene: () => import('./scenes/hello'), length: { bars: 2 }, params: { title: 'Cut on the beat.' }, transition: { kind: 'whip', dir: [1, 0] } },
  ],
});
