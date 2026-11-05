# Round 3 wrap: the last hour on the box (21:30 -> 22:10 UTC power-off, 22:30 hard end)

For agent-07, the only editor driver (or the backup driver, if agent-07 hands over). The box is **powered off by hand by 22:10 UTC** (karmax, agent-10), and the hard end is 22:30.
Run the steps in this order. Each step has a time budget. Every command runs from kali through `film-ue`, but the
work runs **on the box**: `film-ue sh` runs in the box's shell, and `film-ue sync` sends its script to the box. Uploads
go box -> S3 with the box role, in the same region. **Nothing is uploaded from kali, and nothing face-derived goes
anywhere but `.../private/`.**

| # | Step | Budget | By |
|---|---|---|---|
| 1 | Last renders done and checked | 6 min | 21:36 |
| 2 | Deliverables: `cut.sh final --fill-from none` | 10 min | 21:46 |
| 3 | Keep: final_c, cut/ and cal_* -> `private/renders/r3/` (`sync dir up`, SSE-KMS), head-object check, report | 8 min | 21:54 |
| 4 | Save level/project, `sync project up`, `editor stop`, `sync ddc save` (both private), head-object | 10 min | 22:04 |
| 6 | Power the box off by hand, once (3) and (4) are verified | 6 min | 22:10 |
| 5 | kali cleanup (kali only, no box) | 5 min | after 22:10 |
| | slack before the hard end | 20 min | 22:30 |

**The one thing that must hold at the end:** every private upload of anything showing the operator's face (the
frames, `cut/`, the project) is verified `aws:kms` by head-object, and then the box is powered off.

**If you are behind**, drop or defer in this order:
1. the DDC save (4c), which only saves the next box's ~20 min shader compile;
2. then the deliverables (2): the frames are kept in (3), so a later box can cut them again.

**Never skip (3) or the project save (4a/4b).** Step (3) may run in a second background command while (2) encodes:
one uses the CPU and the other the network.

## 0. Before 21:30 (kali, 1 min)

```bash
# the box's checkout of film/host-studio (the one cut.sh runs from; it is at the reel's head)
R=/srv/ue/r3tree     # agent-07's box checkout (tools, reel scripts, fonts, the mixes); confirm it is at the reel's head
B=s3://rf-render-788655295054-aps1/ue-linux/private
film-ue profile show      # region ap-south-1, face_data "yes", kms_key: note it if set (used in step 3)
```

If `face_data` is not `yes`, set it now, before any sync: `film-ue set --face-data yes`.
It makes core refuse any upload outside `.../private/`.

## 1. Last renders done and checked (21:30 -> 21:40)

```bash
film-ue op render.status            # status ok/idle and rendering false: no MRQ job still running
film-ue sh --timeout 900 "cd $R && films/host-studio/reel/r3/cut.sh check final_c V01 V02 V03 V04 V05 S11 S12 N01 S13 S15 S16 S17 S18"
```

- **Name all 13 shots.** `check` with no shot names lists only the shots that have some frames, so a shot that is
  missing entirely would not show up.
- **Pass:** every row has `"missing": 0` and `size` `1920x1080`, and the luma is not black or clipped (compare
  the rows to each other).
- **A shot missing or short:**
  - while a render is still running, wait for it until 21:36 at most (`film-ue op render.status`);
  - otherwise tell agent-10 and agent-05 at once, with `fleetctl tell`, naming the shot and its `first missing`
    frame.
  - Do not start a new render after 21:30: one shot at C takes ~5 min plus warm-up, and steps 2-4 need the editor
    quiet.
  - If a shot is still not final at 21:36, step 2 becomes a rough cut. Run `cut.sh final` without
    `--fill-from none`; the preview stands in, and `cut.json` says so. Say so in the report.

## 2. Deliverables (21:36 -> 21:46)

```bash
film-ue sh --timeout 1800 "cd $R && films/host-studio/reel/r3/cut.sh final --fill-from none"
```

- `--fill-from none` overrides the script's own `--fill-from preview` (argparse takes the last one).
- `assemble.py final` then stops with `not every shot is in: ...` unless every final is there. This is the
  deliverables gate.
- It writes to `/srv/ue/reel/r3/cut/` on the box:
  - `karma-reel-1080p-*.mp4/.mov` and `karma-reel-45s-1080p-*.mp4/.mov`;
  - `.srt` and `.vtt`;
  - `cut.json` and the contact sheet.
- The closing `ls -la` lists them.
- **They show the operator's MetaHuman: they are not pulled to kali** (README, the face rule). They leave the box
  only to `private/renders/r3/cuts/` in step 3. Send karmax and agent-10 the `ls` lines (paths and sizes).
- No-face MP4s may come down to kali's disk (never `/tmp`) through agent-07 or agent-10, but only if karmax asks
  for them.

## 3. Keep: the frames -> private S3, SSE-KMS (21:46 -> 21:54; start the final_c and cal_* syncs alongside step 2 if you are behind)

This is the README's keep step. Run it with `film-ue sync dir up`, **never a raw `aws s3 cp/sync`**. With the box
setting `face_data` set, it refuses any destination outside `.../private/`, and it adds `--sse aws:kms` itself (with
`--sse-kms-key-id` when `kms_key` is set). It runs on the box with the box role: from kali, `film-ue` sends the
script to the box.

```bash
P=s3://rf-render-788655295054-aps1/ue-linux/private/renders/r3
film-ue sync dir up --local /srv/ue/reel/r3/final_c --s3 $P/final_c/ --dry-run   # the script: .../private/... and --sse aws:kms in it
film-ue sync dir up --local /srv/ue/reel/r3/final_c --s3 $P/final_c/   # frames + _render reports; {"ok": true}
film-ue sync dir up --local /srv/ue/reel/r3/cut     --s3 $P/cuts/      # both full cuts (him in them)
film-ue sync dir up --local /srv/ue/reel/r3/cal_C   --s3 $P/cal_C/
film-ue sync dir up --local /srv/ue/reel/r3/cal_A   --s3 $P/cal_A/
film-ue sync dir up --local /srv/ue/reel/r3/cal_B   --s3 $P/cal_B/
film-ue sh 'for d in final_c cut cal_C cal_A cal_B; do echo kept=$d $(find /srv/ue/reel/r3/$d -type f | wc -l); done'
```

- The order puts what matters most first: final_c, then the cuts.
- Each pass's reports (`<pass>/_render/*.report.json`) go with it.
- The previews, the superseded `final/` and the `*_old` folders are not kept.
- The `kept=` lines give the local file counts.

Then check what landed, still on the box (only the box role can read `private/`):

```bash
film-ue sh --timeout 300 '
for k in final_c/0960.png cuts cal_A/_render cal_B/_render cal_C/_render; do
  case $k in */_render|cuts) k=$(aws s3 ls --region ap-south-1 --recursive s3://rf-render-788655295054-aps1/ue-linux/private/renders/r3/$k/ | awk "NR==1{print \$4}") ;; *) k=ue-linux/private/renders/r3/$k ;; esac
  echo "$k"; aws s3api head-object --region ap-south-1 --bucket rf-render-788655295054-aps1 --key "$k" \
    --query "[ServerSideEncryption,SSEKMSKeyId,ContentLength]" --output text
done
for d in final_c cuts cal_A cal_B cal_C; do
  echo $d s3=$(aws s3 ls --region ap-south-1 --recursive --summarize s3://rf-render-788655295054-aps1/ue-linux/private/renders/r3/$d/ | awk "/Total Objects/{print \$3}")
done'
```

- **Pass:**
  - every head-object line starts `aws:kms`, followed by the key ARN (the `kms_key` when one is set);
  - every `s3=` count equals that pass's `kept=` count (`cuts` against `cut`).
  - `final_c/0960.png` is S13's first frame (the operator's MetaHuman). This is the key that matters most.
- **`AES256`, or no `sse`:** stop. That object went up without KMS; the bucket's default is SSE-S3, and the policy
  does not deny unencrypted puts. Tell karmax and agent-10, and do not go on to step 4 until one of them answers.
  Check `film-ue profile show` (`face_data`) and the dry-run's script, then re-run that `sync dir up`. If the
  object still shows `AES256`, leave the fix to karmax.
- **Report before step 4:** send karmax and agent-10 the five `kept=` and `s3=` counts and the head-object
  output, then go on:

  ```bash
  fleetctl tell karmax "r3 keep: final_c/cuts/cal_A/cal_B/cal_C -> s3://rf-render-788655295054-aps1/ue-linux/private/renders/r3/, counts <...>, head-object final_c/0960.png ServerSideEncryption=aws:kms <...>"
  fleetctl tell agent-10 "<the same>"
  ```

## 4. Save the level and project, then the project and DDC -> private (21:54 -> 22:04)

### 4a. Save in the editor

Save in the editor first. `sync project up` refuses while the editor holds unsaved packages, because they are not on
disk yet.

```bash
film-ue op editor.describe          # dirty.maps / dirty.content: what is unsaved
film-ue op level.save               # the open level (/Game/Studio/Studio)
film-ue op assets.save_all          # every other dirty package and map
film-ue op editor.describe          # dirty: both lists empty now
```

### 4b. The project -> `private/project/HostStudio/`

The destination is a box setting. `--project-s3` replaces the whole default path (`s3://<bucket>/ue-projects/<name>`),
so pass it in full without a trailing slash. The same applies to `--ddc-s3`, whose value includes the engine version
(sync.py `project_s3()` / `ddc_s3()`).

```bash
film-ue set --project-s3 s3://rf-render-788655295054-aps1/ue-linux/private/project/HostStudio \
            --ddc-s3     s3://rf-render-788655295054-aps1/ue-linux/private/ddc/5.8.4
film-ue sync project up --dry-run   # the script: destination .../private/project/HostStudio and "--sse aws:kms" in it
film-ue sync project up             # {"ok": true}; up to 2 h timeout, usually minutes (Content changed since 17:00)
```

- The settings live in kali's `film-ue.json` for the current profile. If you work with `--box NAME`, add it to
  every command here.
- Check the dry-run before the real run: both `.../private/` and `--sse aws:kms` must be in the script.
- **Do not edit the set without them.** With `face_data` set, core refuses any destination outside `.../private/`
  (`sync._guard`).
- To a private destination, the face assets travel, as intended: `Content/Host/OperatorCapture`, `Host_Op*` and
  `Unpacked/Host*`.
- `Saved/`, `Intermediate/`, `DerivedDataCache/`, `Binaries/` and `Content/_Selftest/` never travel.
- Capture Manager's converted media (`~/.config/Epic/CaptureManager/...`) is in no sync. Keep it that way.

### 4c. The DDC -> `private/ddc/5.8.4/`

This is the first step to drop when you are late. The DDC save is best with the editor stopped, because the Zen
store is copied as it is otherwise. Stop it only now: steps 1-4b are done and nothing renders.

```bash
film-ue editor stop
film-ue sync ddc save --dry-run     # three aws s3 sync lines to .../private/ddc/5.8.4/{zen-data,engine-ddc,project-ddc}, each with --sse aws:kms
film-ue sync ddc save               # {"ok": true, "skipped": [...]} (a DDC directory that does not exist is skipped, not an error)
```

### 4d. Check and report

Run one head-object per destination, on the box:

```bash
film-ue sh --timeout 300 '
for p in project/HostStudio ddc/5.8.4; do
  k=$(aws s3 ls --region ap-south-1 --recursive s3://rf-render-788655295054-aps1/ue-linux/private/$p/ | awk "NR==1{print \$4}")
  echo "$k"; aws s3api head-object --region ap-south-1 --bucket rf-render-788655295054-aps1 --key "$k" --query ServerSideEncryption --output text
done'
```

- **Pass:** both show `aws:kms`. If one does not, treat it like the step 3 failure.
- Then report to karmax and agent-10: `ok`, the `s3` paths and the head-object lines.
- Leave the editor stopped. The box is powered off next (step 6), and the pre-face DDC from 17:00 under the normal prefix stays as
  it is.

## 6. Power the box off by hand (22:04 -> 22:10)

**This box's instanceInitiatedShutdownBehavior is `terminate`** (agent-07, checked 20:59 UTC on 05 Nov). An OS
shutdown (`sudo shutdown`, `poweroff`, idle-guard.sh, any OS-level TTL) DELETES the instance and its disk. Never power
it off from inside the OS. Use the EC2 stop only:

Only once all of these hold:
- step 3's and step 4's head-objects show `aws:kms`;
- karmax and agent-10 have the report;
- the `/srv/ue/.guard-keepalive` loop of the wrap is stopped.

```bash
film-ue status                      # the instance and its state (running)
film-ue down                        # closes the tunnel, then EC2 stop-instances: the disk survives, private
film-ue status                      # stopping/stopped; again after a minute until stopped
```

- If `film-ue down` does nothing (the `ssh` transport only returns the state), do NOT fall back to an OS shutdown.
  Tell karmax and agent-10 at once, with the instance id.
- Whether to stop or terminate after the saves is cc-64d05f6e's call (asked 21:00 UTC). Until they answer: stop.
- During the wrap (steps 3-4: uploads write no new files, and the GPU is idle once the editor stops), touch
  `/srv/ue/.guard-keepalive` before each sync. Otherwise idle-guard fires 45 min after the last render file, and
  that is a terminate.
- Report the final state (`stopped`) to karmax and agent-10.

## 5. kali cleanup (after 22:10; kali only)

```bash
ls -la /home/nikhil/code/.worktrees/agent-07/out          # list it first (ROUND3: agent-07 deletes it once the shoot is delivered)
du -sh /home/nikhil/code/.worktrees/agent-07/out
# only after the keep step (3) and the project save (4) are reported:
rm -rf /home/nikhil/code/.worktrees/agent-07/out
ls -la /tmp; df -h /tmp                                    # tmpfs (RAM): remove only your own session's files
```

- Delete only what you made: your own `/tmp/fleet-agent-07-*` and scratch files.
- **No Host_Op content on kali or in `/tmp`** (karmax). Anything there that shows the operator's face is deleted
  now, and named in the report.
- Close your `film-ue` tunnel with `film-ue close` before you remove its directory.
- **Never delete another agent's files.**
- The set-shot finals pulled to kali at 16:57 hold no face, but they still go. Say in the report what you deleted.
- Nothing from the box comes down in this step.

## The report (to karmax and agent-10)

The report gives:

- `cut.sh check` (13 shots, missing 0), or what was missing;
- the deliverables' paths and sizes on the box, and their `private/renders/r3/cuts/` copy;
- the keep: the counts, the head-object `aws:kms`, and the `s3://` path;
- the project and DDC: `ok` and the paths, or that the DDC save was skipped for time;
- the kali cleanup;
- whatever was left undone.
