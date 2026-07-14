# Spatial Analytics — Indoor Geofencing & Reporting

This document explains VisionTrack's **indoor geofencing** platform end to end:
what it does, the data model it stands on, how a person on a camera becomes
"Employee X spent 42 minutes at Desk 3", and how operators set it up, view it,
filter it, and export it (CSV + printable PDF).

It's written so an engineer new to the codebase — or a technically-minded
operator — can understand the whole thing without reading every file.

---

## 1. What it does

Given cameras watching a physical space, the platform answers:

- **Occupancy** — how many people are in each zone *right now*, split into
  recognized employees ("known") vs "unknown".
- **Dwell** — which employee spent how long in which zone (department / desk),
  and who is there now.
- **Timeline** — where a single employee was, zone-by-zone, through the day
  ("Sales 09:00–09:45 → Production 09:45–10:30 → …").
- **Attendance** — per employee: arrival, departure, on-site span, total tracked
  time, and how many zones they touched.
- **Zone rollup** — per zone: total person-time, distinct people, average time
  per person, present count (which zones were busiest).

This is "geofencing" done with cameras instead of GPS: **zones are the
geofences, cameras are the sensors, and face-recognition supplies the names.**

---

## 2. Core concepts & data model

| Thing | Where | Meaning |
|---|---|---|
| **Floor plan** | `floor_plans` (JSONB `zones`, `markers`) | A blueprint image. Holds zone polygons and camera markers, both in **fractional 0..1** coordinates. |
| **Zone** | `floor_plans.zones[]` | A named polygon (a department, a desk, an aisle). `{id, name, polygon:[{x,y}], rules}`. |
| **Camera marker** | `floor_plans.markers[]` | A camera's point on the plan: `{camera_id, x, y}`. |
| **Camera calibration** | `cameras.calibration` (JSONB) | Optional BEV **homography** (9 floats) mapping the camera's source-pixel image to floor-plan fractions. Enables desk-level precision. |
| **Track** | `tracks` | One person on one camera: `started_at`, `ended_at`, `last_bbox`, `updated_at`. Its lifetime = the person's presence. |
| **Track point** | `track_points` (TimescaleDB hypertable) | Per-frame position (2 fps sampled). `bbox_*`, and `world_x/world_y` = foot-point projected to floor fractions at ingest **when the camera is calibrated**. |
| **Person identity** | `person_identities` | The face-recognition label (`emp_id`, `name`) correlated onto a track by the FaceTrack bridge. This is the "name". |

**Foot-point:** a person's floor contact is the **bottom-centre of their bbox**
`((x1+x2)/2, y2)`. All projection uses the foot-point so people are placed where
they stand, not where their head is.

---

## 3. Zone attribution — three modes, graceful degradation

The central question is *"which zone is this person in?"*. The answer is resolved
per track, best-available-first. All three modes live in
`analytics/zone_resolve.py` + `analytics/dwell.py`.

1. **Per-track-point (most precise)** — when a track has `world_x/world_y`
   samples (i.e. a calibrated camera), each frame's foot-point is tested against
   the zone polygons and time is **split across the zones the person moved
   through**. A track walking Desk A → Desk B reads as `A: 10m, B: 10m`, not
   `20m` at one desk. `track_zone_intervals` (forward-fill) builds the ordered
   visit intervals; `zone_durations_from_intervals` sums them per zone.

2. **Desk-level (position)** — when the camera is calibrated but per-frame world
   points aren't used (e.g. a live occupancy snapshot), the track's `last_bbox`
   foot-point is projected through the homography and tested against the zone
   polygons. Distinguishes several desks in one camera's view.
   (`resolve_track_zone_refs`, position branch.)

3. **Marker (coarse, fallback)** — when the camera has **no** homography, the
   person is "in" whatever zone(s) the camera's *marker* sits inside. This is the
   original model and needs no calibration.

**Degradation is automatic and per-camera:** uncalibrated deployments work
exactly as before (marker mode); calibrating a camera upgrades only that
camera's tracks to desk-level, and per-track-point weighting kicks in as soon as
world points exist. Nothing has to be turned on globally.

> Occupancy (a live "who's here now" snapshot) intentionally uses **current
> position** (mode 2/3), not time-weighting — instantaneous headcount doesn't
> integrate over time.

---

## 4. The identity bridge (names)

Tracks are anonymous bodies until named. A separate face-recognition pipeline
(FaceTrack) publishes recognition events to a Redis stream
`vt:face:identities:<tenant>`; `persons/face_identity_consumer.py` correlates
each event to an active track (camera + bbox IoU + time) and upserts a
`person_identities` row (`emp_id`, `name`, running `votes`/`confidence`). The
analytics pick the **strongest** identity per track (most votes → confidence →
recency) via `_best_identity_by_track`. No face label ever feeds the tracker —
it's a pure overlay, so a mislabel can't corrupt tracking.

Dwell/timeline/attendance are about **named employees**; anonymous tracks are
dropped from those (but still counted in occupancy's "unknown").

---

## 5. API surface

All endpoints are under `/analytics`, require the `analytics:read` permission,
and are tenant-scoped from the JWT. Ranges are a half-open `[from, to)`; omit
them for "today". Every reporting endpoint accepts the same **filters**:
`from`, `to`, `window` (present-now seconds), `min_seconds`, `emp_id`, `zone_id`.

| Endpoint | Returns |
|---|---|
| `GET /zones/occupancy` | Live per-zone known/unknown headcount (5s refresh). |
| `GET /zones/dwell` · `dwell.csv` | Per (employee, zone) time, visits, first/last seen, present. |
| `GET /zones/rollup` · `rollup.csv` | Per zone: total time, distinct people, avg, present. |
| `GET /attendance` · `attendance.csv` | Per employee: arrival, departure, on-site span, tracked time, zones. |
| `GET /persons/{emp_id}/timeline` · `timeline.csv` | One employee's chronological zone visits. |

`attendance` and `zones/rollup` are **rollups of `get_zone_dwell`**, so all
five stay consistent under the same filters. CSVs guard against spreadsheet
formula injection (`export._safe`) and give durations in both seconds and
`H:MM:SS`.

---

## 6. Calibration (enabling desk-level precision)

Desk-level needs a homography mapping the camera view to the floor plan. The
operator captures it in the UI — **Cameras → ⋮ → Calibrate**:

1. **Capture a frame** from the live stream (freezes a still to click on).
2. Click the **same real-world spot** on the camera still, then on the floor
   plan. Repeat for **4+ well-spread points** (e.g. floor corners).
3. A live **fit-error** readout (mean/max reprojection error) shows quality;
   ≤ 2% is good.
4. **Live projection preview** — recognized people are projected onto the floor
   plan in real time as green dots. If the dots sit where the people really are,
   the calibration is good. This mirrors ingest **exactly** (same
   `footPoint → projectPoint` math), so it's a truthful check.
5. **Save** → writes `cameras.calibration` in the `StoredCalibration` shape:

   ```json
   { "floor_plan_id", "homography": [9 floats], "image_ref": {"width","height"},
     "src_points": [[x,y]…], "dst_points": [[x,y]…], "calibrated_at" }
   ```

The homography maps **source-pixel** coordinates → floor fractions, matching
`tracks.consumer._project_foot` at ingest. Capture at the resolution the pipeline
infers at (usually the stream's native resolution); `image_ref` records what was
used so a scaling step can be added later if resolutions ever diverge.

Math (`frontend/src/modules/bev/homography.ts`): `solveHomography` (4-point DLT),
`projectPoint`, `footPoint`. Verified round-trip and against the backend
projection to ~1e-16.

---

## 7. Reporting (view · filter · export)

**Route:** `/reports/daily` — a bare, chrome-less page (opened in a new tab from
the dwell panel's **Print report** button). It renders a clean white document
with four sections: **Attendance**, **Time in zones**, **By zone**, and
**Movement timelines** (one per employee).

**Filters** (screen-only bar; hidden in print) live in the URL so a filtered
report is shareable/bookmarkable:

- **Date range** — `?from=&to=` or presets (Today, Yesterday, Last 7/30 days,
  This month). Back-compat: `?date=` = single day.
- **Employee**, **Zone**, **Min minutes** — narrow every section and every export.

**Export:**
- **PDF** — the **Print / Save as PDF** button calls `window.print()`; `@page`
  margins + `break-inside-avoid` keep it tidy. Zero dependencies.
- **CSV** — **Attendance CSV**, **Zone CSV**, **Dwell CSV** buttons download the
  server-rendered CSV honouring the *same* filters, so a file matches the screen.

Active filters are printed in the report header for the record.

---

## 8. Operator setup — end to end

1. **Upload a floor plan** (Floor Plans → upload blueprint image).
2. **Place camera markers** — drop each camera onto the plan where it watches.
3. **Draw zones** — polygons for departments and/or desks.
4. *(For desk-level)* **Calibrate** each multi-desk camera (§6) and confirm with
   the live preview.
5. **View analytics** — occupancy/dwell/timeline live on the Analytics page.
6. **Report & export** — open the report, pick a date range + filters, print to
   PDF or download CSV.

If you skip step 4, everything still works at **zone/department** granularity via
marker mode.

---

## 9. Code map

**Backend** (`backend/app/modules/analytics/`):

| File | Responsibility (pure = DB-free, unit-tested) |
|---|---|
| `zone_resolve.py` | pure — `project_foot`, `camera_plan_zones`, `resolve_track_zone_refs`, `point_zone_refs`, `homographies_by_camera` |
| `dwell.py` | pure — `camera_zone_index`, `clip_interval`, `accumulate_dwell`, `track_zone_intervals`, `zone_durations_from_intervals`, `build_person_timeline` |
| `occupancy.py` | pure — `zones_occupancy`, `zones_occupancy_from_tracks` |
| `attendance.py` | pure — `attendance_from_dwell` |
| `zone_report.py` | pure — `zone_rollup_from_dwell` |
| `export.py` | pure — CSV formatters (`dwell_csv`, `attendance_csv`, `zone_rollup_csv`, `timeline_csv`) |
| `service.py` | async DB glue — `get_zone_occupancy/dwell/rollup`, `get_attendance`, `get_person_timeline`, shared `_zone_resolution_context` + `_resolve_tracks_with_zones` |
| `router.py` | HTTP endpoints (JSON + `.csv`) |
| `schemas.py` | Pydantic response models |

**Frontend** (`frontend/src/modules/analytics/`): `api.ts` (hooks +
`download*Csv`), `types.ts`, `AnalyticsPage.tsx`, `ZoneOccupancyPanel`,
`ZoneDwellPanel`, `PersonTimelinePanel`, `DailyReportPage.tsx`; calibration lives
in `modules/cameras/CameraCalibrationDialog.tsx` + `modules/bev/homography.ts`.

---

## 10. Testing

Pure logic is unit-tested (no DB): `tests/test_dwell.py`, `test_zone_resolve.py`,
`test_export.py`, `test_attendance.py`, `test_zone_report.py`.

```bash
cd backend && python -m pytest tests/ -q
```

End-to-end is exercised by `scripts/check_dwell.py` against a **real migrated
Postgres**, seeding zones/cameras/tracks/track_points/identities and asserting
dwell, timeline, desk-level, per-track-point weighting, filters, attendance, and
zone rollup. Run it against a throwaway DB (isolated from any live stack):

```bash
docker run -d --name vt-dwell-test-db -e POSTGRES_USER=visiontrack \
  -e POSTGRES_PASSWORD=visiontrack -e POSTGRES_DB=visiontrack -p 5533:5432 \
  timescale/timescaledb:2.17.0-pg16
docker build -t vt-backend-test backend
RUN='docker run --rm --network host -v '"$PWD"'/backend:/app \
  -e POSTGRES_HOST=localhost -e POSTGRES_PORT=5533 \
  -e POSTGRES_USER=visiontrack -e POSTGRES_PASSWORD=visiontrack -e POSTGRES_DB=visiontrack \
  -e SECRET_KEY=test-secret-key-0123456789abcdef0123 -e APP_ENV=production vt-backend-test'
$RUN alembic upgrade head
$RUN python -m pytest tests/ -q
$RUN python -m scripts.check_dwell
docker rm -f vt-dwell-test-db && docker rmi vt-backend-test
```

Frontend: `npm run typecheck` (in `frontend/`).

---

## 11. Limitations & notes

- **Calibration resolution** — the homography assumes camera clicks and the AI
  worker's bboxes share a pixel space (true when inference resolution == stream
  resolution, the usual case). `image_ref` is stored so an ingest scaling step
  can be added if they diverge.
- **`track_points` scan cost** — per-track-point weighting adds a bounded scan of
  the hypertable (only calibrated tracks in the window, indexed by
  `(track_id, ts)`). It's an analytics query, not real-time; for very large
  sites over long ranges, down-sampling or caps can be added.
- **`present` / "here now"** — computed from an active-window relative to *now*,
  so it's only meaningful for ranges that include the present.
- **Overlapping zones** — a foot-point inside two overlapping polygons counts in
  both; `attendance.tracked_seconds` (sum of per-zone dwell) can therefore exceed
  `span_seconds` (wall-clock arrival→departure).
- **Privacy** — this is biometric/location data about employees. Handle
  retention, access control, and consent per your jurisdiction.
