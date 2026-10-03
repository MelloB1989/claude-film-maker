// Scene API. A scene owns a time window of the song and renders HDR linear colour
// into the render target it is given. Everything must be a deterministic function of
// time (plus internal state advanced only through render() calls, see `stateful`).
import type * as THREE from 'three';
import type { AudioData, AudioSample } from './audio';
import type { VO } from './vo';
import type { Compositor, Layer2D } from './gl';
import type { PostParams } from './post';
import type { Handles } from './transition';

export interface SceneCtx {
  renderer: THREE.WebGLRenderer;
  audio: AudioData;
  vo: VO;
  comp: Compositor;
  W: number;
  H: number;
  /** Timeline entry id and its free-form params (lets one scene module serve several entries). */
  id: string;
  params: Record<string, any>;
  /** Entry window (song seconds). */
  start: number;
  end: number;
}

export interface Frame {
  /** Song time (s). */
  t: number;
  /** Time since the previous rendered frame (1/fps on export; 0 after a seek). */
  dt: number;
  /** Local time since this scene's start, and 0..1 progress through its window. */
  lt: number;
  p: number;
  start: number;
  end: number;
  /** True when time jumped (scrub/seek) — stateful scenes should reset. */
  seeked: boolean;
  /** True while the engine fast-forwards a stateful scene after a seek (skip non-essential work). */
  preroll: boolean;
  /** Continuous beat/bar indices from the analysed grid, and their fractional phases. */
  beat: number;
  bar: number;
  beatPhase: number;
  barPhase: number;
  /** Audio features at t (envelopes 0..1 and decaying hit pulses). */
  a: AudioSample;
}

export type PostOverrides = Partial<PostParams>;

/**
 * A scene's life: constructed, init() once, then prepare() and render() for its frames, then dispose(); it is never
 * inited again (a later need constructs a new one). The player loads every scene at boot. Export constructs and inits
 * each just before a frame first needs it, and a video export disposes it after its last frame, so dispose() must free
 * everything it made: layers (disposeLayer), render targets, textures, geometries, materials, plates.
 */
export abstract class Scene {
  /** If true, the engine fast-forwards (calls render with preroll=true) after seeks. */
  stateful = false;
  /** Max seconds of history the engine re-simulates when seeking into a stateful scene. */
  prerollMax = 6;
  /**
   * How far (s) this scene can render before its start (head) and past its end (tail): a transition side in 'run' mode
   * runs into them (transition.ts sideTime). Only engine-built content may declare any; a plate scene keeps 0, 0 and
   * holds its first or last frame instead.
   */
  handles: Handles = { head: 0, tail: 0 };

  constructor(protected ctx: SceneCtx) {}

  /** Load/create resources. Called once, before the first prepare() and render(). A throw fails an export. */
  init(): Promise<void> | void {}

  /**
   * Optional: load what render() needs at song time t, such as a Blender plate's frame (plates.ts). Export awaits it
   * for every scene on screen in a frame (over its motion-blur shutter) before `still()` and before each streamed
   * frame, so render() can then stay synchronous and exact. The player calls it best-effort, without waiting: there
   * render() must cope with the frame not being loaded yet (Plate.texture shows the nearest one it has).
   */
  prepare?(t: number): Promise<void>;

  /** Reset internal state (called on seeks for stateful scenes). */
  reset(): void {}

  /**
   * Render into `out` (HalfFloat, linear HDR). Must fully overwrite/clear it. Return post-processing overrides. A throw
   * fails an export (the player fills the frame red).
   */
  abstract render(f: Frame, out: THREE.WebGLRenderTarget): PostOverrides | void;

  /** Free everything init() and render() made (see the class doc): export calls it after the scene's last frame. */
  dispose(): void {}
}

export type SceneClass = new (ctx: SceneCtx) => Scene;

/**
 * Free a Layer2D: its texture's GPU copy, and its canvas's backing store (a full-frame layer is 8 MiB at 1080p, 32 MiB
 * at 4K, plus as much again for the texture).
 */
export function disposeLayer(layer: Layer2D) {
  layer.texture.dispose();
  layer.canvas.width = layer.canvas.height = 0;
}
