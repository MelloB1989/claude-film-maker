// The kit's media blocks (films import them as `@kit/media`): a film's screenshots and screen recordings, framed and
// moved. Clips play from frames extracted once by `cd app && bun scripts/media.ts --film <id>` (paths.ts).
export { Image } from './image';
export { Video } from './video';
export { Device, deviceLayout, scrollAt, type DeviceKind } from './device';
export { Framed, cropRect, entryState, kenBurns, layoutBox, type Box, type Entry, type Fit, type KB } from './frame';
export { openSource, type MediaSource, type Picture } from './source';
export { clipFrame, framePath, isVideo, mediaName } from './paths';
