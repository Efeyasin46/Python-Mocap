# Coordinate and code conventions

## Coordinates

- MediaPipe image landmarks: normalized image X/Y and relative Z; not metric.
- MediaPipe world landmarks: metres, X right, Y down, Z depth.
- Nexus viewer: X right, Y depth, Z up; world points are hip-relative.
- Blender/BVH export: X right, Y depth, Z up. Axis conversions belong at an
  explicit boundary, never inside filters.
- Subject anatomical left/right follows MediaPipe labels. Mirroring is preview-only.

## Data integrity

- Video timestamps derive from frame index / source FPS; live timestamps use a
  monotonic clock captured when the frame is acquired.
- Filters must operate on the same coordinate stream consumed by the viewer/export.
- Floor alignment is a clip-level constant offset; it must preserve airborne frames.
- Persisted format changes require a schema version and a migration path.
