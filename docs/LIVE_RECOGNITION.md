# Live Recognition — End to End

How a face recognized by **FaceTrack** becomes a **named person** in the right
**VisionTrack** tenant, with zone dwell/occupancy/attendance attributed to them.

## The loop

```
FaceTrack (DeepStream)                       VisionTrack
──────────────────────                       ───────────
recognises a face on a camera                AI worker tracks bodies on the same
  -> emp_id, name, bbox, time                camera -> Track + TrackPoints
  -> XADD vt:face:identities:<company_id> ─▶  face-identity consumer:
                                               • routes company_id -> tenant
                                               • correlates recognition to a track
                                                 (same camera + bbox IoU + ±1.5s)
                                               • writes person_identities(emp_id,name)
                                             -> employee shows "Recognized";
                                                dwell / occupancy / timeline get NAMED
```

Two independent inputs must land on the **same physical camera**: a **track**
(VisionTrack AI worker) and a **recognition** (FaceTrack). VisionTrack binds them
by `camera_id` + bounding-box IoU (≥ 0.2) within ±1500 ms.

## Verified

`scripts/e2e_recognition.py` exercises the whole loop with the exact data shapes
the live pipeline produces (a Track + TrackPoint + a recognition on the company
stream) — no GPU/camera needed:

```
docker exec vt-backend python -m scripts.e2e_recognition metaxperts
# -> person_identity written: emp_id=786 name="Awais Farooq" conf=0.97 track=correlated
# -> the employee shows recognized=True in that tenant
```

## Going live (real cameras)

Prerequisites: a GPU, a camera reachable by RTSP, and the camera registered in
**both** systems (a shared camera identity). On this shared host, VisionTrack's
`mediamtx`/AI-worker ports (8554/8888/8889) conflict with FaceTrack's — remap them
in an override before bringing them up.

**1. VisionTrack — produce tracks.** Bring up the streaming + AI tiers so a
tenant's cameras generate tracks:

```
docker compose up -d mediamtx ai-worker            # (+ etcd milvus if using ReID)
```

Add the camera in the tenant (Cameras page) with its RTSP URL; note its
**VisionTrack camera UUID**.

**2. FaceTrack (DeepStream) — publish recognitions.** In the company's pipeline
config add a `[visiontrack]` section pointing at VisionTrack's Redis, one entry
per source, keyed by **company_id**:

```toml
[visiontrack]
enabled = true
redis_url = "redis://localhost:6379/0"   # VisionTrack's Redis (host-published)
throttle_sec = 2.0

[[visiontrack.cameras]]
source_id = 0
camera_id = "<VisionTrack camera UUID>"  # the SAME physical camera in VisionTrack
company_id = "<company id>"              # routes to that company's tenant
```

The publisher (`utils/visiontrack_publisher.py`) then `XADD`s each recognition to
`vt:face:identities:<company_id>`. VisionTrack's consumer (Phase 3) already reads
that stream and routes it to the mapped tenant.

**3. Run.** Start the FaceTrack pipeline on the camera. As it recognises faces it
publishes; VisionTrack correlates to its live tracks and names them. Recognized
employees flip to "Recognized"; dwell/occupancy/timeline/attendance show names.

## Notes

- **Reachability:** FaceTrack (host network) reaches VisionTrack's Redis at
  `localhost:6379` (compose publishes it). VisionTrack's container reaches its own
  Redis as `redis:6379`.
- **Shared camera identity:** the `camera_id` FaceTrack publishes MUST equal the
  VisionTrack camera UUID, or recognitions won't correlate to tracks. Keep a
  camera↔camera mapping between the two systems.
- **Single-tenant fallback:** set `tenant_id` instead of `company_id` in the
  `[[visiontrack.cameras]]` entry to publish straight to a tenant stream.
- **Correlation tuning:** `FACE_ID_CORRELATION_WINDOW_MS` (±1500), `FACE_ID_MIN_IOU`
  (0.2) in VisionTrack settings.
