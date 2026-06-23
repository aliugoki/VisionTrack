import { useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Map as MapIcon, Wifi, WifiOff } from 'lucide-react';

import { Card } from '@/shared/components/Card';
import { Select, type SelectOption } from '@/shared/components/Select';
import { Badge } from '@/shared/components/Badge';
import { useAuth } from '@/shared/hooks/useAuth';
import { TRACK_READ } from '@/shared/lib/permissions';
import { useSocket } from '@/shared/hooks/useSocket';
import { useCameras } from '@/modules/cameras/api';
import { useFloorPlans } from '@/modules/floor-plan/api';
import { FloorPlanViewer } from '@/modules/floor-plan/FloorPlanViewer';
import type { TrackUpdateEvent } from '@/modules/tracks/types';
import {
  footPoint,
  projectPoint,
  readCalibration,
  type Homography,
} from '@/modules/bev/homography';

// A track's trail keeps this many recent points (~4s at 10 fps) and is dropped
// entirely once the track goes quiet for TRACK_STALE_MS.
const MAX_TRAIL_POINTS = 40;
const TRACK_STALE_MS = 1500;
const CAM_COLORS = ['#2E9456', '#2563eb', '#d97706', '#dc2626', '#7c3aed', '#0891b2'];

interface TrailPoint {
  x: number; // fractional 0..1 on the floor plan
  y: number;
}
interface Trail {
  pts: TrailPoint[];
  color: string;
}

export default function BEVTrackingPage() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canRead = hasPermission(TRACK_READ);

  const { data: plans } = useFloorPlans();
  const { data: cameras } = useCameras();
  const { socket, connected } = useSocket();

  const [planId, setPlanId] = useState<string>('');
  const plan = useMemo(() => plans?.find((p) => p.id === planId), [plans, planId]);

  // Default to the first floor plan that has a calibrated camera.
  useEffect(() => {
    if (planId || !plans || !cameras) return;
    const calibratedPlanIds = new Set(
      cameras.map((c) => readCalibration(c.calibration)?.floor_plan_id).filter(Boolean)
    );
    const firstPlan = plans.find((p) => calibratedPlanIds.has(p.id)) ?? plans[0];
    if (firstPlan) setPlanId(firstPlan.id);
  }, [plans, cameras, planId]);

  // cameraId -> {homography, color} for cameras calibrated to THIS plan.
  const calibratedCams = useMemo(() => {
    const map = new Map<string, { H: Homography; name: string; color: string }>();
    let i = 0;
    for (const c of cameras ?? []) {
      const cal = readCalibration(c.calibration);
      if (cal && cal.floor_plan_id === planId) {
        map.set(c.id, {
          H: cal.homography,
          name: c.name,
          color: CAM_COLORS[i % CAM_COLORS.length],
        });
        i++;
      }
    }
    return map;
  }, [cameras, planId]);

  // Per-track trail history (key = "cameraId:trackId"), mutated in the socket
  // handler; a counter forces re-render rather than cloning the map each frame.
  const trails = useRef<Map<string, Trail>>(new Map());
  const lastSeen = useRef<Map<string, number>>(new Map());
  const [, bump] = useReducer((n: number) => n + 1, 0);

  // Reset trails when the active plan changes.
  useEffect(() => {
    trails.current.clear();
    lastSeen.current.clear();
    bump();
  }, [planId]);

  useEffect(() => {
    if (!socket || !connected) return;
    const onUpdate = (e: TrackUpdateEvent) => {
      const cal = calibratedCams.get(e.camera_id);
      if (!cal) return; // camera not calibrated for the active plan
      const now = Date.now();
      for (const trk of e.tracks) {
        const [fx, fy] = footPoint(trk.bbox);
        const proj = projectPoint(cal.H, fx, fy);
        if (!proj) continue;
        const [x, y] = proj;
        if (x < 0 || x > 1 || y < 0 || y > 1) continue; // off the plan
        const key = `${e.camera_id}:${trk.track_id}`;
        let tr = trails.current.get(key);
        if (!tr) {
          tr = { pts: [], color: cal.color };
          trails.current.set(key, tr);
        }
        tr.pts.push({ x, y });
        if (tr.pts.length > MAX_TRAIL_POINTS) tr.pts.shift();
        lastSeen.current.set(key, now);
      }
      bump();
    };
    socket.on('track_update', onUpdate);
    return () => {
      socket.off('track_update', onUpdate);
    };
  }, [socket, connected, calibratedCams]);

  // Drop trails for tracks that have gone quiet.
  useEffect(() => {
    const id = setInterval(() => {
      const now = Date.now();
      let changed = false;
      for (const key of Array.from(trails.current.keys())) {
        if (now - (lastSeen.current.get(key) ?? 0) > TRACK_STALE_MS) {
          trails.current.delete(key);
          lastSeen.current.delete(key);
          changed = true;
        }
      }
      if (changed) bump();
    }, 500);
    return () => clearInterval(id);
  }, []);

  if (!canRead) {
    return (
      <Card className="p-8 text-center text-muted-foreground">{t('bev.noReadPermission')}</Card>
    );
  }

  const planOptions: SelectOption[] = (plans ?? []).map((p) => ({ value: p.id, label: p.name }));
  const activeTrails = Array.from(trails.current.entries());
  const liveCount = activeTrails.length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-foreground">
            <MapIcon className="h-6 w-6" />
            {t('bev.title')}
          </h1>
          <p className="text-sm text-muted-foreground">{t('bev.subtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={connected ? 'success' : 'danger'} dot pulse={connected}>
            {connected ? (
              <Wifi className="me-1 inline h-3 w-3" />
            ) : (
              <WifiOff className="me-1 inline h-3 w-3" />
            )}
            {connected ? t('bev.live') : t('bev.offline')}
          </Badge>
          <Badge tone="primary">{t('bev.peopleLive', { count: liveCount })}</Badge>
        </div>
      </div>

      <div className="max-w-xs">
        <Select
          label={t('bev.floorPlan')}
          options={planOptions}
          placeholder={t('bev.selectFloorPlan')}
          value={planId}
          onChange={(e) => setPlanId(e.target.value)}
        />
      </div>

      {calibratedCams.size === 0 && plan && (
        <Card className="p-4 text-sm text-muted-foreground">{t('bev.noCalibratedCameras')}</Card>
      )}

      {plan ? (
        <Card className="p-2">
          <div className="h-[600px]">
            <FloorPlanViewer plan={plan}>
              {() => (
                <svg
                  className="pointer-events-none absolute inset-0"
                  width={plan.width_px}
                  height={plan.height_px}
                  style={{ overflow: 'visible' }}
                >
                  {activeTrails.map(([key, tr]) => {
                    if (tr.pts.length === 0) return null;
                    const W = plan.width_px;
                    const H = plan.height_px;
                    const head = tr.pts[tr.pts.length - 1];
                    const pointsStr = tr.pts
                      .map((p) => `${p.x * W},${p.y * H}`)
                      .join(' ');
                    return (
                      <g key={key}>
                        {/* Fading movement trail */}
                        <polyline
                          points={pointsStr}
                          fill="none"
                          stroke={tr.color}
                          strokeWidth={3}
                          strokeOpacity={0.5}
                          strokeLinejoin="round"
                          strokeLinecap="round"
                        />
                        {/* Current position (head) */}
                        <circle
                          cx={head.x * W}
                          cy={head.y * H}
                          r={7}
                          fill={tr.color}
                          stroke="#fff"
                          strokeWidth={2}
                        />
                      </g>
                    );
                  })}
                </svg>
              )}
            </FloorPlanViewer>
          </div>
          {/* Camera legend */}
          {calibratedCams.size > 0 && (
            <div className="flex flex-wrap gap-3 px-2 pt-2">
              {Array.from(calibratedCams.entries()).map(([id, c]) => (
                <span key={id} className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: c.color }} />
                  {c.name}
                </span>
              ))}
            </div>
          )}
        </Card>
      ) : (
        <Card className="p-8 text-center text-muted-foreground">{t('bev.selectFloorPlan')}</Card>
      )}
    </div>
  );
}
