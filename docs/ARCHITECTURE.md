# MotionForge architecture

## Current pipeline

```mermaid
flowchart LR
  A[Camera or video] --> B[OpenCV frames]
  B --> C[MediaPipe Holistic]
  C --> D[MocapFrame normalized + world landmarks]
  D --> E[Filters and floor alignment]
  E --> F[JSON recording]
  F --> G[3D viewer]
  F --> H[BVH and Blender JSON export]
```

The current implementation is a desktop prototype. Capture and bake own their
processing loops; `MocapFrame` is the persisted interchange model. The world
landmark coordinates are metres with MediaPipe axes (X right, Y down, Z depth).

## Target pipeline

```mermaid
flowchart LR
  A[sources: camera / video / IP] --> B[perception: PoseBackend]
  B --> C[MotionClip tensors + timestamps]
  C --> D[core: coordinates, rig, filters, kinematics]
  D --> E[io: versioned JSON / BVH / glTF / OSC]
  E --> F[app: capture, playback, timeline, settings]
```

The target separates hardware and GUI dependencies from pure motion processing.
`MocapFrame` remains as a compatibility reader while new recordings migrate to
a versioned clip format. This is incremental: existing launch scripts remain
usable during migration.
