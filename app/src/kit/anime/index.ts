// The anime kit (films import it as `@kit/anime`): blocks for shots made from generated key art and clips
// (docs/PIPELINE-ANIME.md). Parallax lays painted plates and cut-out characters at depths under a moving camera, and
// PlateShot plays a Blender plate; Rain, Mist, Smoke, Rays, Paper and SpeedLines are the weather, the air and the
// manga marks over them; PostKeys animates the frame's grade, strobes, shakes and letterbox; InkReveal brushes
// calligraphy on; Words and Subtitles set the type. Clips play through `@kit/media` Video, under any of these in a Stack.
export { Parallax, cameraAt, drift, type LayerSpec, type CameraMove, type CameraKey } from './parallax';
export { PlateShot } from './plateshot';
export { Rain, rainClock, lightningAt } from './rain';
export { Mist, Smoke, Rays, Paper } from './atmos';
export { SpeedLines } from './speedlines';
export { PostKeys, trackAt, type Keys, type Track } from './postkeys';
export { InkReveal } from './inkreveal';
export { Words, type WordLine } from './words';
export { Subtitles, cueAlpha, type Cue } from './subtitles';
