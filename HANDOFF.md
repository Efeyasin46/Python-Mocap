# HANDOFF — read this first (written 2026-11-19, late evening)

Previous agent was asked to "move the project forward" and to leave a note if
the work was left unfinished. All 4 Todo items now have an implementation
(all in *Review*, none verified on real camera/MediaPipe data).
Board: `docs/TASKS.md`.

## Done this session

**MotionClip + JSON v2 migration** (moved to *Review*, not *Done*, because no
human has looked at it and nothing was run against real MediaPipe/Qt).

- `src/core/motion_clip.py` (new): pure numpy/stdlib `MotionClip`.
  Tensors `image` / `world` shaped `(T, J, 4)` = x, y, z, confidence; absent
  joint = NaN coords + confidence 0 (stored as JSON `null`). Also holds
  `timestamps`, `frame_ids`, `confidence_avg`, `fps`, `source`, sparse
  `frame_meta` / `frame_bones`, and free `meta`.
  `from_frames()` / `to_frames()` bridge to `MocapFrame`; `from_dict()` accepts
  v1 (bare list) and v2 and raises `ClipFormatError` otherwise.
- `src/core/frame_model.py`: `UnifiedExporter.save_recording` now writes v2;
  `load_recording` reads v1 or v2 and still returns `List[MocapFrame]`, so
  capture / bake / viewer / export_blender needed no changes. New
  `UnifiedExporter.load_clip()` returns the `MotionClip`.
- `tests/test_motion_clip.py` (new, 11 tests, all pass): lossless round trip,
  v1 migration, NaN joints, empty clip, mixed sources, bad files.
- `pyproject.toml`: added `pythonpath = ["src"]` to pytest config.

Run tests: `python -I -m pytest -q` from the project root.

**BVH exporter rewrite** (moved to *Review*)

- `src/core/bvh_exporter.py` rewritten; `BVHExporter(frames).export(path)` keeps
  its signature, so `export_blender.py` is unchanged (checked end to end on
  synthetic data: v2 recording -> Blender JSON + BVH + Unity JSON).
- Reads `MotionClip.world`. Derived joints (Hips, Spine, Spine1, Neck, Head,
  clavicles) are built from landmarks; bone lengths are clip-constant medians
  (L/R averaged); rest pose is a T-pose with identity orientations.
- Axis conversion lives only in `mp_to_bvh`: BVH = (x, -y, -z). Matches the
  Unity exporter's convention. Channels `Zrotation Xrotation Yrotation`,
  matrix = Rz @ Rx @ Ry, angles unwrapped over time. Units: `scale=100` (cm).
- Low-confidence (<0.2) / missing samples are interpolated; a landmark absent for
  the whole clip leaves that bone at rest (zero rotation). If no `world`
  data exists it falls back to image coords scaled to a 0.5 m torso.
- Fixed old bugs: wrong joint->bone name mapping, fake Euler angles, fps off by
  one frame interval, no derived spine/head.
- `tests/test_bvh_exporter.py`: independent BVH parser + forward kinematics
  confirms exported angles reproduce landmark positions (atol 2 mm); also gaps,
  missing limbs, missing hips (ValueError), 360-degree yaw continuity.
- Limits: no arm/leg twist (swing only); feet/hands/leaf joints are not oriented
  (inherit parent, no toe/finger solve); spine twist all lands on Spine1; root
  X/Z translation is ~0 because MediaPipe world space is hip-centred (height
  only changes if the clip was floor aligned, as bake does). Never opened in
  Blender - import one exported file and eyeball it first.

**Synthetic fixtures + headless bake filters** (moved to *Review*)

- `src/core/bake_filters.py` (new): `BakeFilters` = the exact filter chain that
  was inline in `bake.py` (drop compensation -> smoothing -> foot lock ->
  `is_valid`, then depth de-jitter + constant floor offset via `finalize`).
  `bake.py` now calls it; behaviour intended to be identical, but `bake.py`
  itself could only be byte-compiled here (see mediapipe note below).
- `tests/helpers.py` (new): `synth_frames` (articulated pose with known joint
  truth), BVH parser + FK, `render_video` (stick-figure mp4 via cv2, generated
  into `tmp_path` at test time; `*.mp4`/`*.json` are gitignored, so nothing is
  committed).
- `tests/test_pipeline_integration.py` (new): video timing (frame idx / fps),
  jitter reduction, drop compensation limit (5 frames), floor offset constant and
  airborne frames preserved, and capture-file -> Blender JSON + BVH + Unity JSON.
- Sandbox has mediapipe 0.10.32 (no `mp.solutions`), but the project pins
  0.10.21, so `bake.py` / `capture.py` cannot be imported here. The synthetic
  video is NOT fed through real MediaPipe inference; a stick figure would not be
  detected anyway. A real-footage regression clip is still needed for that.
- Observation, not changed: `MocapFrame.is_valid()` falls back to image `joints`
  when `world_joints` is empty, so a frame with image but no world landmarks is
  kept with empty world data. Real MediaPipe loses both together, so low risk.

**Playback timeline + recording library** (moved to *Review*; UI part unverified)

- `src/core/playback.py` (new, pure logic): `PlaybackTimeline` - relative time,
  `advance(dt)`, loop / no-loop (stops at end, toggle restarts), speed 0.1-4x,
  reverse, A-B loop range, `seek`, `seek_frame`, `step` (pauses), O(log n) frame
  lookup via searchsorted, `position` = (i, j, alpha) for interpolation (unused
  by the viewer yet). Repairs non-monotonic timestamps, safe for 0/1 frames.
- `src/core/library.py` (new, pure logic): `RecordingLibrary(data_dir).scan()`
  returns `RecordingInfo` (kind, schema version, frames, duration, fps, source,
  size, mtime) for v1/v2 recordings only; Blender/Unity/report JSONs and
  calibration.json are classified out (`include_exports=True` shows exports).
  Cached by (mtime, size); `delete()` refuses paths outside the data folder.
- `src/viewer.py` now uses `PlaybackTimeline` instead of the O(n) scan per
  tick: renders only when the frame index changes (so ghost trails no longer
  accumulate duplicates while paused), keys: Space play/pause, Left/Right step,
  `[` `]` speed, R reverse, L loop, Home/End; state shown in the window title.
  The GL widget is set to NoFocus so the window receives keys.
  **Only byte-compiled here - never run with Qt/OpenGL. Test it by hand.**
- NOT done (needs Qt and eyes): an on-screen scrub slider / transport bar, a
  library panel in `launcher.py` (its open dialogs still list every `*.json` in
  `data/`, including exports; `library.scan()` is ready to feed a list widget),
  and drawing interpolated frames via `timeline.position`.
- `MocapFrame.get_world_coords` re-normalizes per frame, so very low playback
  speeds look the same as before; no change there.

## Known gaps / things I did NOT verify

- Never ran capture, bake or the viewer (no camera, no MediaPipe, no PyQt/GL
  here). Only unit tests, plus one headless run of `export_blender.py` on
  synthetic landmarks.
- v2 files are written compact (no indent), unlike the old `indent=4`. Files
  are not human-diffable any more; revisit if that matters.
- pytest config has `env = [...]`, which needs `pytest-env`; it is not in the
  `dev` extra, so pytest warns "Unknown config option: env". I did not touch
  dependencies because `uv.lock` would go stale. `pytest-qt` is also not
  installed in the sandbox, so Qt tests could not be tried.
- `.gitignore` ignores `*.json`; fixtures you add as JSON need `git add -f` or
  a `!tests/fixtures/*.json` rule.
- `README.md` is a single line; `README_v2.8.txt` describes features (confidence
  matrix, frame-drop compensator, bone clamping) that I did not check against
  the code. Don't trust it as a spec.
- `src/__pycache__`, `*.egg-info` shipped inside the zip; harmless but ignored
  by git anyway.
- The `.json` recordings the user already has are v1; they load fine via the
  migration but are only rewritten as v2 if re-saved (e.g. by bake).

## Suggested next steps (in order)

1. **Review** the MotionClip change; run one real capture -> bake -> viewer
   -> Blender export on a machine with a camera or a video file.
2. Import an exported `.bvh` into Blender and check orientation / facing /
   scale; if wrong, fix only `mp_to_bvh` and the rest-pose directions.
3. Add one short real-footage clip (with permission, small) as a bake regression
   fixture on a machine with MediaPipe 0.10.21.
4. Manually run `python src/viewer.py data/<some recording>.json` and check the
   keys listed above; then build the Qt pieces: transport bar + slider bound to
   `PlaybackTimeline`, and a library list in the launcher fed by `RecordingLibrary`.

## Rules to keep (from `docs/CONVENTIONS.md`)

Any persisted-format change needs a schema version and a migration path;
filters must work on the same coordinates the viewer/export consume; mirroring
is preview-only.
