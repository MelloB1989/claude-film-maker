# unreal/linux: the editor on a Linux GPU box with no desktop

`film-ue` drives a Linux box the same way it drives the Windows workstation: the bridge (`unreal/fmbridge`) runs
inside the editor on 127.0.0.1:18765 and is reached through an SSM port-forward; commands and files go over SSM
(`AWS-RunShellScript`), big folders through S3. What differs is how the editor runs: **offscreen, under systemd**, with
no desktop, no DCV and no login. Background and sources: `docs/linux/workflow.md`.

```
film-ue (any machine with the AWS CLI + Session Manager plugin)       Linux GPU box (Ubuntu 22.04, L4)
  --box linux op / exec / install ──SSM port-forward──▶ 127.0.0.1:18765  fmbridge in UnrealEditor
                                                                         ue-editor.service: -RenderOffscreen -unattended
  provision / editor / desktop    ──SSM RunShellScript─▶ setup.sh steps (root) / files as the editor's user
  push-dir / pull-dir             ──S3──▶ aws s3 sync on the box
```

## Files

- `setup.sh`: idempotent steps, run as root: `volume` (the data disk at /srv/ue), `driver` (NVIDIA 580-server +
  Vulkan), `engine` (from S3 with the build's `ue-restore.sh`), `project` (from S3) or `windisk` + `project-copy` (from
  a Windows workstation's disk: an EBS volume made from its snapshot, mounted read-only), `service`, `desktop on|off`,
  `check`.
- `ue-editor.sh` → `/usr/local/bin/ue-editor`: the editor's command line, from `/etc/default/ue-editor`.
- `ue-editor.service`: the systemd unit (`Restart=on-failure`), as the editor's user (the engine refuses root).

## Use

```bash
cd tools
uv run film-ue --box linux set --os linux --instance i-0123456789abcdef0 --region ap-south-1 --bucket my-bucket \
    --local-port 18766
uv run film-ue --box linux provision --engine-s3 s3://my-bucket/ue-linux --version 5.8.4 \
    --project-src win:UEProjects/Demo --project Demo --level /Game/Maps/Main      # or --project-src s3://...
uv run film-ue --box linux install          # the bridge into Content/Python; the editor (re)started by systemd
uv run film-ue --box linux health           # engine, platform: linux, project
uv run film-ue --box linux op seq.stills ...  # every op as on Windows
uv run film-ue --box linux editor log 200   # the journal
uv run film-ue --box linux down
```

`FILM_UE_BOX=linux` does the same as `--box linux` for scripts that import `filmtools.unreal.client`. Film code
must not hard-code a project path: use `workstation.project("Saved", "Stills")`, which joins in the box's own style.

## No desktop: what changes

- `film-ue screen` and `film-ue gui` answer 501: there is no desktop. Pictures come from the engine (`look.still`,
  `seq.still`, `seq.stills`, renders).
- Dialogs: `-unattended` suppresses them; ops must never do anything that would open one (export over an asset,
  close an unsaved level). A dialog that still appears blocks the game thread: `film-ue editor restart`.
- Renders: `render.mrq` in the editor (`executor="pie"`) or in its own `-game -RenderOffscreen` process
  (`executor="process"`), which survives a crash and leaves the editor free.

## A sign-in (Epic account: Fab, MetaHuman cloud services)

The one thing code cannot do is type someone's password. `film-ue --box linux desktop on` starts Xorg on the GPU
with a virtual 1920x1080 screen, openbox, Firefox and x11vnc on the box's 127.0.0.1:5900, restarts the editor onto
that screen (without `-unattended`, so the sign-in dialog shows), and forwards the VNC port here through SSM: open
`vnc://localhost:5901` (macOS: Finder > Go > Connect to Server) with the password in `/root/vnc-pass` on the box (root only, never
printed: read it in your own session with `sudo cat`). Sign in, then
`film-ue --box linux desktop off`: the editor goes back offscreen. Nothing listens on a public port at any time.

## The proof of concept

`film-ue --box linux poc 1,2,3,4,5,6,7 ...` (`tools/filmtools/unreal/poc.py`): GPU and engine; the editor and bridge
offscreen; stills with no display; MRQ in the editor and in its own process, compared frame by frame with a
reference render; audio to face; MetaHuman cloud services; a soak. Each writes `poc-out/pocN.json`.
