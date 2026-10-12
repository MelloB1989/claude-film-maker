// Music analysis sampled at any film time: the beat grid, sections, loudness envelopes and onsets that tools/ film-beats
// (or film-temptrack) writes to films/<id>/data/audio.json. A film without one gets a synthetic grid from its BPM
// (AudioData.grid): beat-locked motion works the same, the envelopes read 0 and there are no onsets.
import { filmUrl } from './config';

export interface AudioJSON {
  duration: number;
  bpm: number;
  fps: number;
  /** Beats per bar (default 4). */
  time_signature?: number;
  beats: number[];
  downbeats: number[];
  sections: { name: string; start: number; end: number }[];
  features: Record<string, number[]>;
  onsets: Record<string, [number, number][]>;
}

export interface AudioSample {
  rms: number; low: number; mid: number; high: number;
  vocal: number; drums: number; bass: number; other: number;
  /** Decaying pulses (1 at the hit, half-life ~90-140 ms), scaled by hit strength. */
  kick: number; snare: number; hat: number; vonset: number;
}

const FEATURES = ['rms', 'low', 'mid', 'high', 'vocal', 'drums', 'bass', 'other'] as const;

export class AudioData {
  duration: number;
  bpm: number;
  beats: number[];
  downbeats: number[];
  sections: { name: string; start: number; end: number }[];
  /** Beats per bar (the score's time signature; 4 unless the analysis says otherwise). */
  beatsPerBar: number;
  private fps: number;
  private feat: Record<string, Float32Array> = {};
  onsets: Record<string, [number, number][]>;

  constructor(j: AudioJSON) {
    this.duration = j.duration;
    this.bpm = j.bpm;
    this.beats = j.beats;
    this.downbeats = j.downbeats;
    this.sections = j.sections ?? [];
    this.beatsPerBar = j.time_signature ?? 4;
    this.fps = j.fps || 100;
    // envelopes may be nested under `features` or top-level arrays
    for (const k of FEATURES) this.feat[k] = Float32Array.from(j.features?.[k] ?? ((j as any)[k] as number[] | undefined) ?? []);
    this.onsets = j.onsets ?? {};
  }

  /** Load an analysis (default: the film's data/audio.json). */
  static async load(url = filmUrl('data/audio.json')): Promise<AudioData> {
    const r = await fetch(url);
    if (!r.ok || !(r.headers.get('content-type') ?? '').includes('json')) throw new Error(`audio analysis ${url}: HTTP ${r.status} (run tools/ film-beats or film-temptrack, or give the film a bpm instead)`);
    return new AudioData(await r.json());
  }

  /**
   * A synthetic, perfectly even grid: a beat every 60/bpm s from `offset` (the first downbeat) to `duration`, a downbeat
   * every `beatsPerBar` beats, one section, no envelopes or onsets. What a film without an analysed score cuts to.
   */
  static grid(o: { duration: number; bpm?: number; offset?: number; beatsPerBar?: number }): AudioData {
    const bpm = o.bpm ?? 120, offset = o.offset ?? 0, bpb = o.beatsPerBar ?? 4, period = 60 / bpm;
    if (!(bpm > 0) || !(bpb >= 1)) throw new Error(`a beat grid needs bpm > 0 and beatsPerBar >= 1 (got ${bpm}, ${bpb})`);
    const beats: number[] = [];
    for (let i = 0, t = offset; t <= o.duration + 1e-9; i++, t = offset + i * period) beats.push(+t.toFixed(6));
    const downbeats = beats.filter((_, i) => i % bpb === 0);
    return new AudioData({
      duration: o.duration, bpm, fps: 100, time_signature: bpb, beats, downbeats,
      sections: [{ name: 'all', start: 0, end: o.duration }], features: {}, onsets: {},
    });
  }

  /** Linear-interpolated envelope value at time t. */
  env(name: string, t: number): number {
    const a = this.feat[name];
    if (!a || a.length === 0) return 0;
    const x = t * this.fps;
    const i = Math.floor(x);
    if (i < 0) return a[0]!;
    if (i >= a.length - 1) return a[a.length - 1]!;
    const f = x - i;
    return a[i]! * (1 - f) + a[i + 1]! * f;
  }

  /** Max over [t - w, t]: a peak-hold for punchy reactions. */
  envPeak(name: string, t: number, w = 0.08): number {
    let m = 0;
    for (let s = t - w; s <= t; s += 1 / this.fps) m = Math.max(m, this.env(name, s));
    return m;
  }

  /** Sum of decaying pulses from onsets of a kind (kick/snare/hat/vocal) before t. */
  hit(kind: string, t: number, halfLife = 0.11): number {
    const list = this.onsets[kind];
    if (!list || list.length === 0) return 0;
    let lo = 0, hi = list.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (list[m]![0] <= t) lo = m + 1; else hi = m; }
    let v = 0;
    for (let i = lo - 1; i >= 0 && i >= lo - 6; i--) {
      const [ot, s] = list[i]!;
      const dt = t - ot;
      if (dt > halfLife * 8) break;
      v = Math.max(v, s * Math.pow(0.5, dt / halfLife));
    }
    return v;
  }

  /** Onset events of a kind in [t0, t1). */
  events(kind: string, t0: number, t1: number): [number, number][] {
    return (this.onsets[kind] ?? []).filter(([t]) => t >= t0 && t < t1);
  }

  sample(t: number): AudioSample {
    return {
      rms: this.env('rms', t), low: this.env('low', t), mid: this.env('mid', t), high: this.env('high', t),
      vocal: this.env('vocal', t), drums: this.env('drums', t), bass: this.env('bass', t), other: this.env('other', t),
      kick: this.hit('kick', t, 0.12), snare: this.hit('snare', t, 0.14), hat: this.hit('hat', t, 0.06),
      vonset: this.hit('vocal', t, 0.15),
    };
  }

  /** Continuous beat index: 0 at first beat, fractional in between (extrapolated outside). */
  beatAt(t: number): number {
    const b = this.beats;
    if (b.length < 2) return t * (this.bpm / 60);
    if (t <= b[0]!) return (t - b[0]!) / (b[1]! - b[0]!);
    if (t >= b[b.length - 1]!) {
      const p = b[b.length - 1]! - b[b.length - 2]!;
      return b.length - 1 + (t - b[b.length - 1]!) / p;
    }
    let lo = 0, hi = b.length - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (b[m]! <= t) lo = m; else hi = m; }
    return lo + (t - b[lo]!) / (b[hi]! - b[lo]!);
  }

  /** Time of (fractional) beat index. */
  timeOfBeat(i: number): number {
    const b = this.beats;
    const n = b.length;
    const period = n > 1 ? (b[n - 1]! - b[0]!) / (n - 1) : 60 / this.bpm;
    if (i <= 0) return (b[0] ?? 0) + i * period;
    if (i >= n - 1) return b[n - 1]! + (i - (n - 1)) * period;
    const k = Math.floor(i);
    return b[k]! + (b[k + 1]! - b[k]!) * (i - k);
  }

  /** Continuous bar index from downbeats (0 at first downbeat). */
  barAt(t: number): number {
    const d = this.downbeats;
    if (d.length < 2) return this.beatAt(t) / this.beatsPerBar;
    if (t <= d[0]!) return (t - d[0]!) / (d[1]! - d[0]!);
    if (t >= d[d.length - 1]!) {
      const p = d[d.length - 1]! - d[d.length - 2]!;
      return d.length - 1 + (t - d[d.length - 1]!) / p;
    }
    let lo = 0, hi = d.length - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (d[m]! <= t) lo = m; else hi = m; }
    return lo + (t - d[lo]!) / (d[hi]! - d[lo]!);
  }

  /** Nearest beat time to t. */
  nearestBeat(t: number): number {
    return this.timeOfBeat(Math.round(this.beatAt(t)));
  }

  /** Nearest downbeat time to t. */
  nearestDownbeat(t: number): number {
    const d = this.downbeats;
    if (d.length < 2) return this.timeOfBeat(Math.round(this.beatAt(t) / this.beatsPerBar) * this.beatsPerBar);
    let best = d[0]!;
    for (const x of d) if (Math.abs(x - t) < Math.abs(best - t)) best = x;
    return best;
  }

  /** Time of (fractional) bar index (the inverse of barAt). */
  timeOfBar(i: number): number {
    const d = this.downbeats;
    if (d.length < 2) return this.timeOfBeat(i * this.beatsPerBar);
    const n = d.length, period = (d[n - 1]! - d[0]!) / (n - 1);
    if (i <= 0) return d[0]! + i * period;
    if (i >= n - 1) return d[n - 1]! + (i - (n - 1)) * period;
    const k = Math.floor(i);
    return d[k]! + (d[k + 1]! - d[k]!) * (i - k);
  }

  section(t: number) {
    return this.sections.find((s) => t >= s.start && t < s.end) ?? this.sections[this.sections.length - 1];
  }
}
