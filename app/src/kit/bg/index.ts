// The kit's animated backgrounds (films import them as `@kit/bg`): shader blocks, pure functions of time, configured by
// params (base.ts lists the ones they share). Each stands alone as a shot, or under type in a Stack (`@kit/stack`).
export { BgScene, hotInk, inkLevel, pulseAt, type BgParams, type Pulse } from './base';
export { Aurora } from './aurora';
export { MeshGradient } from './mesh';
export { Grid } from './grid';
export { Particles } from './particles';
export { Warp, pulseArea, warpTravel } from './warp';
