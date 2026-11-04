# film-ue doctor (B11)

The first command on a new box, and the first thing to run when something odd happens:

```bash
film-ue doctor            # NOT READY / OK, then one line per problem with its fix
film-ue doctor --json     # {"pass", "issues": [{"code": "doctor.*", "severity", "message", "fix"}], "metrics"}
film-ue op editor.doctor  # the editor's half alone
```

## What it checks

**On the client** (`tools/filmtools/unreal/cli_doctor.py`):

- The box settings exist.
- The bridge answers `/health`. When it does not, the fix names `film-ue editor status/log` on Linux, or
  `film-ue up/install` on Windows.

**In the editor** (`editor.doctor`, read-only):

| check | failure severity | fix |
|---|---|---|
| engine is 5.8 | warn | run the selftests before trusting the ops |
| editor Python is 3.11 | warn | |
| not `-nullrhi` | fail | restart without it |
| `-unattended` (not Windows) | warn | a modal dialog would hang the editor |
| plugins: PythonScriptPlugin, EditorScriptingUtilities, MovieRenderPipeline, SequencerScripting | fail | enable in the .uproject, restart |
| plugins: LevelSequenceEditor, MetaHumanCharacter, MetaHuman (Animator) | warn | |
| plugin: Fab | info | |
| every op module imported (`ops.broken` empty) | fail | `film-ue op ops.broken`, fix, `film-ue install` |
| free disk on the project volume ≥ `min_free_gb` (50) | warn, or fail under 10 GB | clear Saved/MovieRenders |
| Epic sign-in stored (Linux `~/.local/share/.eos_sdk`) | warn | `film-ue epic-login` |
| `unreal.MoviePipelineQueueSubsystem`, `MetaHumanCharacterEditorSubsystem`, `LevelSequenceEditorBlueprintLibrary`, `DataLayerEditorSubsystem` exposed | warn | enable the plugin |
| `r.HairStrands.SkyLighting` is 0 | info | `editor.cvar` (the README trap) |

## API_NOTES

| Python | source |
|---|---|
| `PluginBlueprintLibrary.get_enabled_plugin_names()` (also `is_plugin_mounted`) | Runtime/Engine/Public/PluginBlueprintLibrary.h:47, 181 |
| `SystemLibrary.get_command_line()` | Runtime/Engine/Classes/Kismet/KismetSystemLibrary.h:2046 |
| `SystemLibrary.get_console_variable_int_value` | KismetSystemLibrary.h (used by editor.cvar too) |
| Plugin names | Engine/Plugins/MovieScene/MovieRenderPipeline, MovieScene/SequencerScripting, MovieScene/LevelSequenceEditor, MetaHuman/MetaHumanCharacter, MetaHuman/MetaHumanAnimator (MetaHuman.uplugin), Fab, Experimental/PythonScriptPlugin |
