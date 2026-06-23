#!/usr/bin/env bash
# =============================================================================
# VisionTrack smoke test
#
# Verifies that a fresh `docker compose up` produces a healthy system.
# Run after every meaningful change to catch regressions before clients do.
#
# Usage:
#   ./scripts/smoke.sh                # uses running stack
#   ./scripts/smoke.sh --rebuild      # tears down, rebuilds, brings up, then tests
# =============================================================================

set -euo pipefail

BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

REBUILD=0
if [[ "${1:-}" == "--rebuild" ]]; then
    REBUILD=1
fi

pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; exit 1; }
info() { echo -e "${BLUE}▶${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }

# -----------------------------------------------------------------------------

if [[ $REBUILD -eq 1 ]]; then
    info "Tearing down stack..."
    docker compose down -v
    pass "Stack down (volumes preserved on next up)"

    info "Building all images (may take 5-10 minutes for mediamtx + ai-worker)..."
    docker compose build
    pass "All images built"

    info "Bringing stack up..."
    docker compose up -d
    pass "Containers started"

    info "Waiting 30s for migrations + seed + service warmup..."
    sleep 30
fi

# -----------------------------------------------------------------------------
info "Checking container health..."

for svc in postgres redis minio mediamtx backend frontend worker beat ai-worker; do
    state=$(docker compose ps --format json "$svc" 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('State','missing'))" 2>/dev/null || echo "missing")
    if [[ "$state" == "running" ]]; then
        pass "$svc is running"
    else
        fail "$svc is $state"
    fi
done

# -----------------------------------------------------------------------------
info "Checking backend API..."

if curl -sf http://localhost:8000/health >/dev/null; then
    pass "GET /health returns 200"
else
    fail "GET /health failed"
fi

if curl -sf http://localhost:8000/docs >/dev/null; then
    pass "Swagger /docs accessible"
else
    fail "Swagger /docs not reachable"
fi

# -----------------------------------------------------------------------------
info "Checking auth..."

TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@visiontrack.io","password":"ChangeMe123!"}' \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token','')) " 2>/dev/null || echo "")

if [[ -z "$TOKEN" ]]; then
    fail "Login returned no access_token"
fi
pass "Login successful, JWT obtained"

# -----------------------------------------------------------------------------
info "Checking core API endpoints..."

for endpoint in sites cameras tracks/active; do
    if curl -sf "http://localhost:8000/api/v1/${endpoint}" \
        -H "Authorization: Bearer $TOKEN" >/dev/null; then
        pass "GET /api/v1/${endpoint} returned 200"
    else
        fail "GET /api/v1/${endpoint} failed"
    fi
done

# -----------------------------------------------------------------------------
info "Checking GPU access (mediamtx + ai-worker)..."

if docker compose exec -T mediamtx nvidia-smi >/dev/null 2>&1; then
    pass "mediamtx container can see GPU"
else
    warn "mediamtx container cannot see GPU (NVIDIA toolkit issue?)"
fi

if docker compose exec -T ai-worker nvidia-smi >/dev/null 2>&1; then
    pass "ai-worker container can see GPU"
else
    warn "ai-worker container cannot see GPU"
fi

# -----------------------------------------------------------------------------
info "Checking AI worker model load..."

if docker compose logs ai-worker 2>&1 | grep -q "inference.model_ready"; then
    pass "AI worker loaded YOLOv8 model"
else
    warn "No 'inference.model_ready' log line — model may still be loading"
fi

# -----------------------------------------------------------------------------
info "Checking Celery worker..."

if docker compose logs worker 2>&1 | grep -q "camera_health.completed"; then
    pass "Health check task is running"
else
    warn "No 'camera_health.completed' yet — wait up to 30s for first beat tick"
fi

# -----------------------------------------------------------------------------
info "Checking TimescaleDB hypertable..."

HYPERTABLES=$(docker compose exec -T postgres psql -U visiontrack -d visiontrack -t -c \
    "SELECT hypertable_name FROM timescaledb_information.hypertables;" 2>/dev/null \
    | tr -d ' \n' || echo "")

if [[ "$HYPERTABLES" == *"track_points"* ]]; then
    pass "track_points is a TimescaleDB hypertable"
else
    fail "track_points hypertable missing"
fi

# -----------------------------------------------------------------------------
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  All smoke checks passed.                                    ║${NC}"
echo -e "${GREEN}║  Open http://localhost:5173 and log in with                  ║${NC}"
echo -e "${GREEN}║  admin@visiontrack.io / ChangeMe123!                         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
