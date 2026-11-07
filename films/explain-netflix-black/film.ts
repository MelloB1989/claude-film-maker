// The Netflix graphics over black (no studio): one of the two passes films/explain-netflix/tools/alpha.py turns into
// straight alpha. Everything is films/explain-netflix's; only the matte differs.
import { netflixFilm } from '../explain-netflix/film';
import config from './film.json';

export default netflixFilm(config, 'black');
