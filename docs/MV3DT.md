# MV3DT — Multi-View 3D Tracking (design + scaffold + runbook)

Status: **design-stage**. Not implemented. This document is the plan, the proposed
data model, the service interfaces, and an ordered runbook. No runtime code is wired
in by this document (deliberately — see "Why not yet" below).

Author note (2026-06-09): produced as the design/scaffold half of the "BEV + MV3DT"
work. The **BEV** half shipped (per-camera image→floor-plan homography, live top-down
view). MV3DT is the cross-camera fusion layer that sits on top of BEV.

---

## 1. What MV3DT is

NVIDIA **MV3DT** (Multi-View 3D Tracking, part of the Metropolis / DeepStream
multi-camera tracking — "mtmc" — stack) fuses person tracks from many overlapping
or non-overlapping cameras into a single **global identity** with a position in a
shared **3D / floor-plan world frame**, across time. Output: one trajectory per
physical person across the whole site, not per-camera track fragments.

Two complementary signals drive it:
1. **Spatial-temporal** — where each detection is on the shared floor (requires camera
   calibration: intrinsics + extrinsics, or at minimum a ground-plane homography per
   camera) and when. Tracks that occupy the same world location at the same time, or
   that hand off plausibly between adjacent cameras, are the same person.
2. **Appearance (ReID)** — OSNet embeddings disambiguate when geometry is ambiguous
   (crowds, occlusion, non-overlapping gaps).

VisionTrack already has **both** building blocks:
- Appearance: the **P2.5 matcher** + `person_embeddings` + OSNet producer (shipped).
- Spatial: the **BEV homographies** in `cameras.calibration` (shipped) give each
  camera an image→floor-plan(0..1) projection — the ground-plane half of calibration.

So MV3DT in VisionTrack = **fuse BEV world-positions + ReID embeddings + time** into
global cross-camera trajectories.

---

## 2. Why not yet (prerequisites / blockers)

1. **GPU/DeepStream path is blocked.** NVIDIA's MV3DT runs in the DeepStream/Metropolis
   pipeline, and our DeepStream worker (`ai-worker-ds`) is blocked by the pyds
   metadata-dispatch segfault (see `~/visiontrack-checkpoints/p2-3-deferred/RUNBOOK.md`).
   The real NVIDIA tracker is not reachable until that's resolved.
2. **Extrinsic calibration missing.** True 3D MV3DT needs per-camera extrinsics
   (pose in world frame) and ideally intrinsics. We currently have only ground-plane
   homographies (enough for floor-plan fusion, not full 3D).
3. **Overlap topology unknown.** Cross-camera handoff modeling needs the camera
   adjacency / overlap graph for the site.

**Therefore:** the pragmatic path is a **software geometric+appearance fusion** built on
the shipped BEV + matcher — no DeepStream, no GPU — which delivers most of MV3DT's
business value (site-wide trajectories) now, and treats NVIDIA MV3DT as the eventual
GPU-accelerated upgrade once the DeepStream blocker clears.

---

## 3. Proposed data model (DDL sketch — Alembic migration 0016, NOT yet applied)

Builds on existing `persons` (appearance identity) and `tracks` (per-camera). Adds the
spatial/global-trajectory layer.

```sql
-- Per-camera pose in the site's world/floor frame. Ground-plane homography
-- already lives in cameras.calibration; this adds full extrinsics when available.
CREATE TABLE camera_extrinsics (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    camera_id       uuid NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    floor_plan_id   uuid NOT NULL REFERENCES floor_plans(id) ON DELETE CASCADE,
    rotation        jsonb,        -- 3x3 R (optional, for full 3D)
    translation     jsonb,        -- 3-vec t (optional)
    intrinsics      jsonb,        -- fx,fy,cx,cy,dist (optional)
    -- ground-plane homography is read from cameras.calibration (already present)
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, camera_id, floor_plan_id)
);

-- A global, cross-camera trajectory (one physical person moving through the site).
-- Distinct from persons: persons = "who" (appearance identity, long-lived);
-- global_tracks = "one visit/journey" (a contiguous spatial-temporal path).
CREATE TABLE global_tracks (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    person_id       uuid REFERENCES persons(id) ON DELETE SET NULL,  -- appearance link
    floor_plan_id   uuid NOT NULL REFERENCES floor_plans(id) ON DELETE CASCADE,
    started_at      timestamptz NOT NULL,
    ended_at        timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_global_tracks_tenant_time ON global_tracks (tenant_id, started_at);

-- Maps per-camera Track fragments to a global track (many cameras -> one journey).
ALTER TABLE tracks ADD COLUMN global_track_id uuid
    REFERENCES global_tracks(id) ON DELETE SET NULL;
CREATE INDEX ix_tracks_global ON tracks (global_track_id);

-- Fused world-frame positions sampled along a global track (for BEV trail replay).
-- TimescaleDB hypertable, mirrors track_points conventions (no FKs, ts PK).
CREATE TABLE global_track_points (
    ts              timestamptz NOT NULL,
    global_track_id uuid NOT NULL,
    tenant_id       uuid NOT NULL,
    world_x         double precision NOT NULL,  -- floor-plan fractional (0..1)
    world_y         double precision NOT NULL,
    contributing_camera_id uuid,
    confidence      double precision,
    PRIMARY KEY (ts, global_track_id)
);
```

Note: `cameras.calibration` (homography) and `track_points.world_x/world_y` (reserved)
already exist — the BEV work began populating the spatial layer.

---

## 4. Service interface sketch (`backend/app/modules/mv3dt/` — proposed, not created)

```python
# fusion.py  (proposed)
class MultiViewFuser:
    """Software cross-camera fusion. Runs as a periodic sweep like PersonMatcher.

    Inputs (already produced today):
      - track_points with world_x/world_y  (BEV-projected ground positions)
      - person_embeddings + persons        (OSNet appearance identity, P2.5)
    Output:
      - global_tracks + global_track_points + tracks.global_track_id
    """
    async def fuse_window(self, db, tenant_id, t0, t1) -> None:
        # 1. Gather per-camera track fragments active in [t0,t1] with world positions.
        # 2. Build spatial-temporal candidate links: fragments whose world positions
        #    coincide (distance < eps) at overlapping times, OR hand off across an
        #    adjacency edge within a time gap.
        # 3. Gate/confirm each candidate link with ReID cosine similarity (reuse the
        #    matcher's embedding space + threshold).
        # 4. Union-find the confirmed links into global tracks; assign global_track_id;
        #    write fused global_track_points (e.g. weighted by per-camera confidence).
        ...
```

Runtime: a `MultiViewFuser` background task in `app.main` lifespan, **mirroring
`PersonMatcher`** (the matcher is the template — same session/commit/idempotency model).
Gated by a `MV3DT_ENABLED` flag (default False until validated).

---

## 5. Integration with the shipped pieces

```
ai-worker (OSNet) ──embeddings──▶ matcher ──▶ persons (WHO)         ┐
                                                                     ├─▶ MultiViewFuser ─▶ global_tracks
BEV homographies ──project──▶ track_points.world_x/y (WHERE)        ┘        │
                                                                            ▼
                                                          BEV page: global trajectories / heatmaps
```

The BEV live page already renders per-camera projected dots; once fusion runs, it can
render **stitched global trajectories** (one colored trail per `global_track`) instead
of disconnected per-camera dots.

---

## 6. Runbook (ordered; software-fusion first, NVIDIA MV3DT later)

Each step lists the gate to pass before the next.

### Phase A — Software floor-plan fusion (no GPU, buildable now)
1. **Persist world positions.** Project `track_points` foot-points through
   `cameras.calibration.homography` at ingest (extend `tracks/consumer.py`) OR in a
   batch backfill. Gate: `track_points.world_x/world_y` populated for calibrated cams.
2. **Migration 0016** (the DDL in §3). Gate: `alembic upgrade head` + downgrade clean.
3. **MultiViewFuser** (§4) as a periodic sweep. Start with spatial-only linking
   (world distance + time), then add ReID gating. Gate: synthetic two-camera overlap
   test → one global track spanning both (mirror the matcher's seeded-embedding test).
4. **BEV trajectories** in the UI: render `global_track_points` trails. Gate: visual.
5. Checkpoint.

### Phase B — Calibration depth (improves accuracy)
6. **Extrinsics capture UI** (extend the BEV calibration page): collect enough
   correspondences for pose, populate `camera_extrinsics`. Gate: re-projection error
   below threshold on held-out points.
7. **Camera adjacency graph** for the site (which cameras can hand off). Gate: editable
   in the floor-plan editor.

### Phase C — NVIDIA MV3DT (GPU, blocked on DeepStream)
8. **Unblock DeepStream** — resolve the pyds segfault first
   (`p2-3-deferred/RUNBOOK.md`). Gate: SGIE+probe stable >60s.
9. **Stand up the Metropolis mtmc / MV3DT** config against `ai-worker-ds`; feed it the
   extrinsics from §6. Gate: NVIDIA tracker emits global IDs on the GPU.
10. **A/B** NVIDIA MV3DT vs the software fuser on the same footage; switch the fuser to
    consume NVIDIA global IDs when it wins. Gate: accuracy + throughput compared.
11. Checkpoint (code + db + engine).

### Hard prerequisites before Phase C
- DeepStream pyds blocker resolved.
- Per-camera extrinsic calibration (Phase B).
- A GPU with headroom beyond the current YOLO+OSNet load.

---

## 7. Honest scope note
Phase A is genuinely achievable in software and reuses everything shipped this session.
Phase C ("real NVIDIA MV3DT") depends on an unresolved native blocker and hardware
calibration data, and is multi-week + GPU-verified — it is **not** an overnight task.
Recommend building Phase A next; treat Phase C as a roadmap item gated on the DeepStream
fix.
```
