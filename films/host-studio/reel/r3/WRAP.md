# Round 3 wrap: the last hour on the box (21:30 -> 22:30 UTC)

For agent-07, the only editor driver (or the backup driver, if agent-07 hands over). The box ends at **22:30 UTC**.
Run the steps in this order. Each step has a time budget. Every command runs from kali through `film-ue`, but the
work runs **on the box**: `film-ue sh` runs in the box's shell, and `film-ue sync` sends its script to the box. Uploads
go box -> S3 with the box role, in the same region. **Nothing is uploaded from kali, and nothing face-derived goes
anywhere but `.../private/`.**

| # | Step | Budget | By |
|---|---|---|---|
| 1 | Last renders done and checked | 10 min | 21:40 |
| 2 | Deliverables: `cut.sh final --fill-from none` | 15 min | 21:55 |
| 3 | Keep: frames -> `private/renders/r3/` (SSE-KMS), head-object check, report | 10 min | 22:05 |
| 4 | Save level/project, `sync project up`, `editor stop`, `sync ddc save` (both private) | 15 min | 22:20 |
| 5 | kali cleanup | 5 min | 22:25 |
| | slack | 5 min | 22:30 |

**If you are behind**, drop or defer in this order:
1. the DDC save (4c), which only saves the next box's ~20 min shader compile;
2. then the deliverables (2): the frames are kept in (3), so a later box can cut them again.

**Never skip (3) or the project save (4a/4b).** Step (3) may run in a second background command while (2) encodes:
one uses the CPU and the other the network.

## 0. Before 21:30 (kali, 1 min)

```bash
# the box's checkout of film/host-studio (the one cut.sh runs from; it is at the reel's head)
R=<the box checkout>
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
  - while a render is still running, wait for it until 21:40 at most (`film-ue op render.status`);
  - otherwise tell agent-10 and agent-05 at once, with `fleetctl tell`, naming the shot and its `first missing`
    frame.
  - Do not start a new render after 21:40: one shot at C takes ~5 min plus warm-up, and steps 2-4 need the editor
    quiet.
  - If a shot is still not final at 21:45, step 2 becomes a rough cut. Run `cut.sh final` without
    `--fill-from none`; the preview stands in, and `cut.json` says so. Say so in the report.

## 2. Deliverables (21:40 -> 21:55)

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
- Leave them on the box: **the orchestrator pulls the MP4s.** Send karmax the `ls` lines, the paths and sizes,
  as soon as it finishes, so the pull runs while you do steps 3 and 4.
- **Pull them before 22:30**: the box (and its disk) ends then.

## 3. Keep: the frames -> private S3, SSE-KMS (21:55 -> 22:05)

This is the README's keep step, run on the box with the box role. Add `--sse-kms-key-id <kms_key>` to `KMS` only
when step 0 showed a `kms_key`.

```bash
film-ue sh --timeout 2400 '
set -e
KMS="--sse aws:kms"          # + " --sse-kms-key-id <kms_key>" when the box setting is set
for d in final_c cal_A cal_B cal_C; do
  aws s3 sync --only-show-errors --no-progress --region ap-south-1 /srv/ue/reel/r3/$d s3://rf-render-788655295054-aps1/ue-linux/private/renders/r3/$d/ $KMS
  echo kept=$d $(find /srv/ue/reel/r3/$d -type f | wc -l)
done'
```

- Each pass's reports (`<pass>/_render/*.report.json`) go with it.
- The previews are not kept.
- The `kept=` lines give the local file counts.

Then check what landed, still on the box (only the box role can read `private/`):

```bash
film-ue sh --timeout 300 '
for k in final_c/0960.png cal_A/_render cal_B/_render cal_C/_render; do
  case $k in */_render) k=$(aws s3 ls --region ap-south-1 --recursive s3://rf-render-788655295054-aps1/ue-linux/private/renders/r3/$k/ | awk "NR==1{print \$4}") ;; *) k=ue-linux/private/renders/r3/$k ;; esac
  echo "$k"; aws s3api head-object --region ap-south-1 --bucket rf-render-788655295054-aps1 --key "$k" \
    --query "[ServerSideEncryption,SSEKMSKeyId,ContentLength]" --output text
done
for d in final_c cal_A cal_B cal_C; do
  echo $d s3=$(aws s3 ls --region ap-south-1 --recursive --summarize s3://rf-render-788655295054-aps1/ue-linux/private/renders/r3/$d/ | awk "/Total Objects/{print \$3}")
done'
```

- **Pass:**
  - every head-object line starts `aws:kms`, followed by the key ARN (the `kms_key` when one is set);
  - every `s3=` count equals that pass's `kept=` count.
  - `final_c/0960.png` is S13's first frame (the operator's MetaHuman). This is the key that matters most.
- **`AES256`, or no `sse`:** stop. That object went up without KMS; the bucket's default is SSE-S3, and the policy
  does not deny unencrypted puts. Tell karmax and agent-10, and do not go on to step 4 until one of them answers.
  Usually the fix is a re-copy in place with KMS:
  `aws s3 cp --recursive s3://.../r3/<d>/ s3://.../r3/<d>/ --sse aws:kms --metadata-directive REPLACE`, on the box.
- **Report before step 4:** send karmax and agent-10 the four `kept=` and `s3=` counts and the head-object
  output, then go on:

  ```bash
  fleetctl tell karmax "r3 keep: final_c/cal_A/cal_B/cal_C -> s3://rf-render-788655295054-aps1/ue-linux/private/renders/r3/, counts <...>, head-object final_c/0960.png ServerSideEncryption=aws:kms <...>"
  fleetctl tell agent-10 "<the same>"
  ```

## 4. Save the level and project, then the project and DDC -> private (22:05 -> 22:20)

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
- Leave the editor stopped. The box ends at 22:30, and the pre-face DDC from 17:00 under the normal prefix stays as
  it is.

## 5. kali cleanup (22:20 -> 22:25; kali only, may run after 22:30)

```bash
ls -la /home/nikhil/code/.worktrees/agent-07/out          # list it first (ROUND3: agent-07 deletes it once the shoot is delivered)
du -sh /home/nikhil/code/.worktrees/agent-07/out
# only after the orchestrator confirms the deliverables are pulled and the keep step is reported:
rm -rf /home/nikhil/code/.worktrees/agent-07/out
ls -la /tmp; df -h /tmp                                    # tmpfs (RAM): remove only your own session's files
```

- Delete only what you made: your own `/tmp/fleet-agent-07-*` and scratch files.
- Close your `film-ue` tunnel with `film-ue close` before you remove its directory.
- **Never delete another agent's files.**
- The set-shot finals pulled to kali at 16:57 hold no face, but they still go. Say in the report what you deleted.
- Nothing from the box comes down in this step.

## The report (to karmax and agent-10)

The report gives:

- `cut.sh check` (13 shots, missing 0), or what was missing;
- the deliverables' paths and sizes on the box, and whether karmax has pulled them;
- the keep: the counts, the head-object `aws:kms`, and the `s3://` path;
- the project and DDC: `ok` and the paths, or that the DDC save was skipped for time;
- the kali cleanup;
- whatever was left undone.
