# Deploying FaceTrack + VisionTrack — Complete Guide

A step-by-step guide anyone can follow to stand up **both** systems and make them
work together, including the new **zone occupancy** feature (count people in an area,
split into *known* employees vs *unknown* people).

No prior knowledge assumed. Copy-paste the commands in order.

---

## 0. What are these two systems? (plain English)

You are deploying **two products that team up**:

| System | Answers the question | What it does |
|---|---|---|
| **FaceTrack** | **Who?** | Recognizes employees' **faces** on camera → marks **attendance** (checked in/out, on-time/late). |
| **VisionTrack** | **Where / how many?** | Tracks **people's bodies** across cameras → **zones, counting, movement, alerts**. |

Used together they answer: **"How many people are in Zone A right now, and how many of
them are known employees vs unknown?"** FaceTrack supplies the *names*; VisionTrack does
the *counting per area*.

**You do not have to run both.** If you only need attendance, deploy FaceTrack.
If you only need people-counting, deploy VisionTrack. The "known vs unknown" split needs
**both**, connected (Section 4).

---

## 1. One-time prerequisites (the server)

You need one **Linux server (Ubuntu 22.04+) with an NVIDIA GPU** and your cameras'
**RTSP URLs** (e.g. `rtsp://user:pass@192.168.1.10:554/stream`).

Install the basics (run once, as a user who can `sudo`):

```bash
# Docker + Compose
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"          # log out and back in after this

# NVIDIA driver (if not already) + container toolkit so Docker can use the GPU
sudo apt update && sudo apt install -y nvidia-driver-535 nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker

# sanity check — both should succeed:
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

---

## 2. Deploy VisionTrack (people-counting)

```bash
cd /path/to/visiontrack

# 1) Set your own passwords/secrets before first boot:
nano backend/.env         # change POSTGRES_PASSWORD, JWT secret, admin password

# 2) Start everything (Postgres, Redis, MinIO, MediaMTX, backend, workers, frontend):
make up                   # first boot ~2 minutes (downloads + migrations + seeding)
make logs                 # watch until it settles
```

Open the dashboard and sign in:

- **URL:** `http://<server-ip>:5173`
- **Email:** `admin@visiontrack.io`  **Password:** `ChangeMe123!` → **change it immediately** (top-right user menu).

Then set up your space (left sidebar):
1. **Configuration → Cameras** — add each camera with its RTSP URL. It appears in the live wall.
2. **Configuration → Floor Plans** — upload a picture/map of your building.
3. On the floor plan: **draw zones** (aisles, rooms, wings) and **place a camera marker**
   for each camera at its real location on the map.

> That last step is what makes counting work: a zone "contains" the cameras whose
> markers you dropped inside it.

---

## 3. Deploy FaceTrack (attendance)

FaceTrack lives in its own repo (`attendance-system` + `deepstream`). Its full guide is
**`DEPLOYMENT.md`** in that repo. Short version:

```bash
cd /path/to/attendance-system
cp backend/.env.example backend/.env && nano backend/.env    # DB, secrets, AGENT_TOKEN
./deploy/deploy.sh                                           # dashboard on :5002
sudo ./deploy/install-agent.sh                              # the pipeline agent (systemd)
```

Then in the FaceTrack dashboard: create a company, add its cameras, **enroll employees'
faces**, and **Pipeline → Start** to launch its recognition pipeline.

Moving to a different server/GPU? See `DEPLOYMENT.md` §12 (rebuild the GPU engines with
`tools/rebuild-engines.sh`).

---

## 4. Connect the two (so "known vs unknown" works)

The FaceTrack pipeline **tells VisionTrack who each person is** by publishing to
VisionTrack's Redis. VisionTrack matches that name onto the body it's already tracking.

**Requirements (all must be true):**
1. **Both systems watch the SAME physical camera.** FaceTrack recognizes the face and
   VisionTrack tracks the body *of the same person on the same stream*. If they watch
   different cameras, names can't be matched.
2. FaceTrack knows that camera's **VisionTrack IDs** (a camera UUID + a tenant UUID).
3. VisionTrack's **Redis** is reachable from the FaceTrack pipeline host.
4. The FaceTrack pipeline image includes the `redis` Python library (now built in — if
   you built the image before this change, **rebuild it**:
   `docker build -t deepstream-facepipe:latest -f Dockerfile.facepipe .`).

**Steps:**

1. Get the VisionTrack IDs. In VisionTrack, open the camera you want (Cameras page) —
   its URL/details show the **camera UUID**; your **tenant UUID** is on the tenant/settings
   page. (Or ask your admin / read them from the DB.)

2. In the **FaceTrack** pipeline config (`deepstream/config/config_pipeline.toml`, or the
   template it's generated from), enable the publisher and map each pipeline camera to its
   VisionTrack IDs:

   ```toml
   [visiontrack]
   enabled = true
   redis_url = "redis://<visiontrack-host>:6379/0"
   throttle_sec = 2.0

   # one block per camera; source_id 0 = the pipeline's first camera, 1 = second, …
   [[visiontrack.cameras]]
   source_id = 0
   camera_id = "8a0b2ad4-....-....-....-............"   # VisionTrack camera UUID
   tenant_id = "4ae93489-....-....-....-............"   # VisionTrack tenant UUID
   ```

3. Restart that company's pipeline (FaceTrack **Pipeline → Restart**).

4. **Verify** it's flowing:
   ```bash
   # On the VisionTrack host — you should see face events arriving:
   docker compose exec redis redis-cli XLEN vt:face:identities:<tenant_id>
   # And in VisionTrack's DB, labels appearing:
   docker compose exec postgres psql -U visiontrack -d visiontrack \
     -c "select emp_id, name, votes from person_identities order by last_labeled_at desc limit 5;"
   ```

If Redis is down or a camera is unmapped, publishing is **safely skipped** — FaceTrack's
attendance keeps working regardless.

---

## 5. Use it — count people in a zone (known vs unknown)

In **VisionTrack → Monitoring → Analytics**, the **"Live zone occupancy"** section shows,
for every zone, updating every 5 seconds:

- **Present now** — total people currently in the zone.
- **✓ known** (green) — recognized employees, with their names listed.
- **! unknown** (amber) — tracked people with no identity yet.

**How the number is produced (so you can trust/debug it):** a zone's people = the active
tracks on the cameras whose markers sit inside that zone (Section 2, step 3). A person is
**known** when the FaceTrack bridge (Section 4) has named their track; otherwise **unknown**.

There's also an API if you want to pull it into another system:
```
GET /api/v1/analytics/zones/occupancy        (requires an analytics-read token)
→ { as_of, active_window_sec, zones: [{ zone_name, total, known, unknown, known_people:[…] }] }
```

---

## 6. Troubleshooting

| You see | Likely cause & fix |
|---|---|
| **"Live zone occupancy" is empty** | No zones/markers drawn yet (Section 2, step 3), or the people-tracking worker isn't producing tracks — check `docker compose logs ai-worker`. |
| **Everyone shows as "unknown"** | The bridge isn't connected. Work through Section 4: same camera in both systems, correct camera/tenant UUIDs, Redis reachable, and the pipeline image has `redis` (rebuild it). |
| **Counts look too high/low** | Occupancy is per-camera (a proxy for area). Make sure each camera's marker is inside the right zone and cameras don't double-cover an area. |
| **VisionTrack won't start** | `make logs` — usually a port already in use or a bad value in `backend/.env`. VisionTrack needs ports 5173/8000/5432/6379/8554/8888/9000; don't run it on the same host+ports as FaceTrack without remapping. |
| **FaceTrack faces not recognized** | See the FaceTrack repo's `DEPLOYMENT.md` troubleshooting (face too small/too far, or rebuild GPU engines after a hardware change). |

---

## 7. Who does what (roles)

- **VisionTrack** roles: *Tenant Admin* (everything), *Supervisor* (ops + reports + alerts),
  *Operator* (monitoring + acknowledge), *Viewer* (read-only). Set on the Users/Roles pages.
- **FaceTrack** roles: *super_admin* (companies + pipelines), *admin* (own company),
  *manager*/*viewer* (reports/read). See the FaceTrack `USER_GUIDE.md`.

---

## 8. Everyday commands

```bash
# VisionTrack
make up / make down / make logs / make ps      # start / stop / logs / status
make migrate                                   # apply DB migrations

# FaceTrack
docker compose up -d --build                   # (in attendance-system) update the dashboard
systemctl status facetrack-agent               # the pipeline agent
```

That's it. Deploy VisionTrack (Section 2), deploy FaceTrack (Section 3), connect them
(Section 4), and read your zone occupancy in VisionTrack's Analytics (Section 5).
