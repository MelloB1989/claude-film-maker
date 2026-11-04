"""WP8 Sequencer core (seq.* ops beyond the older ones in ops/seq.py). The pure, engine-free modules (_time, _curves,
_model, _spec, _plan) also load on the client through tools/filmtools/unreal/seq_spec.py; _engine is the unreal side;
seq_core registers the ops (auto-discovered). Guide: docs/unreal/sequencer.md."""
