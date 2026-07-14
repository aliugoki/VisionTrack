import { useEffect, useMemo, useRef, useState } from 'react';
import Hls from 'hls.js';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Camera as CamIcon, Crosshair, Undo2, Eraser, Loader2 } from 'lucide-react';
import { Dialog } from '@/shared/components/Dialog';
import { Button } from '@/shared/components/Button';
import { FloorPlanViewer } from '@/modules/floor-plan/FloorPlanViewer';
import { useFloorPlans } from '@/modules/floor-plan/api';
import { useUpdateCamera } from '@/modules/cameras/api';
import {
  solveHomography,
  projectPoint,
  footPoint,
  type StoredCalibration,
} from '@/modules/bev/homography';
import { getLatestFrame } from '@/modules/tracks/useTrackEvents';
import type { Camera } from '@/shared/types/api';
import type { FloorPlan } from '@/modules/floor-plan/types';

/**
 * Camera → floor-plan calibration.
 *
 * The operator marks the SAME real-world spot on the live camera view and on the
 * floor plan, four or more times. From those correspondences we solve the planar
 * homography (``bev/homography.solveHomography``) that maps a person's foot-point
 * in the camera image to fractional floor-plan coordinates — which is exactly
 * what the desk-level zone analytics need (``Camera.calibration.homography``).
 *
 * Camera-side points are recorded in the captured frame's intrinsic pixel space
 * (stored as ``image_ref``); floor-plan points are fractional 0..1. This matches
 * the ingest projection (``tracks.consumer._project_foot``), which applies the
 * homography to source-pixel bboxes.
 */

const COLORS = ['#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#a855f7', '#ec4899', '#14b8a6', '#f97316'];

type Pt = [number, number];
interface Pair {
  src: Pt; // camera pixels
  dst: Pt; // floor fraction 0..1
}

function normalizeHlsUrl(url: string): string {
  if (url.startsWith('/')) return url;
  try {
    return `/hls${new URL(url).pathname}`;
  } catch {
    return url;
  }
}

// ---- Camera view with freeze-frame capture + click-to-mark ---------------- //

interface CaptureProps {
  hlsUrl: string;
  srcPoints: Pt[];
  draft: Pt | null;
  onPoint: (p: Pt, w: number, h: number) => void;
}

function CameraCaptureSurface({ hlsUrl, srcPoints, draft, onPoint }: CaptureProps) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const [ready, setReady] = useState(false);
  const [frozen, setFrozen] = useState<{ url: string; w: number; h: number } | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = true;
    video.playsInline = true;
    const url = normalizeHlsUrl(hlsUrl);
    setReady(false);

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = url;
      const onPlaying = () => setReady(true);
      video.addEventListener('playing', onPlaying);
      void video.play().catch(() => {});
      return () => {
        video.removeEventListener('playing', onPlaying);
        video.removeAttribute('src');
        video.load();
      };
    }
    if (!Hls.isSupported()) return;
    const hls = new Hls({ liveSyncDuration: 3, manifestLoadingMaxRetry: 8 });
    hlsRef.current = hls;
    hls.attachMedia(video);
    hls.on(Hls.Events.MEDIA_ATTACHED, () => hls.loadSource(url));
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      setReady(true);
      void video.play().catch(() => {});
    });
    return () => {
      hls.destroy();
      hlsRef.current = null;
    };
  }, [hlsUrl]);

  function freeze() {
    const v = videoRef.current;
    if (!v || !v.videoWidth || !v.videoHeight) {
      toast.error(t('cameras.calibration.notReady'));
      return;
    }
    const c = document.createElement('canvas');
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    const ctx = c.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(v, 0, 0, c.width, c.height);
    try {
      setFrozen({ url: c.toDataURL('image/jpeg', 0.9), w: v.videoWidth, h: v.videoHeight });
    } catch {
      toast.error(t('cameras.calibration.captureFailed'));
    }
  }

  function handleClick(e: React.MouseEvent<HTMLDivElement>) {
    if (!frozen) return;
    const img = e.currentTarget.querySelector('img');
    const rect = (img || e.currentTarget).getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const x = ((e.clientX - rect.left) / rect.width) * frozen.w;
    const y = ((e.clientY - rect.top) / rect.height) * frozen.h;
    onPoint([Math.max(0, Math.min(frozen.w, x)), Math.max(0, Math.min(frozen.h, y))], frozen.w, frozen.h);
  }

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-muted-foreground">
          {t('cameras.calibration.cameraView')}
        </span>
        {frozen ? (
          <Button variant="ghost" onClick={() => setFrozen(null)}>
            {t('cameras.calibration.retake')}
          </Button>
        ) : (
          <Button variant="secondary" onClick={freeze} disabled={!ready}>
            <CamIcon className="mr-1 h-4 w-4" />
            {t('cameras.calibration.capture')}
          </Button>
        )}
      </div>

      <div className="relative flex-1 overflow-hidden rounded-md bg-black">
        {/* Live video is hidden once a frame is frozen (kept mounted so retake is instant). */}
        <video
          ref={videoRef}
          className={frozen ? 'hidden' : 'h-full w-full object-contain'}
          muted
          playsInline
        />
        {!frozen && !ready && (
          <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        )}
        {!frozen && ready && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-black/50 px-2 py-1 text-center text-[11px] text-white">
            {t('cameras.calibration.captureHint')}
          </div>
        )}

        {frozen && (
          <div className="relative h-full w-full cursor-crosshair" onClick={handleClick}>
            <img src={frozen.url} alt="frame" className="h-full w-full select-none object-contain" draggable={false} />
            {srcPoints.map((p, i) => (
              <Marker key={i} xPct={(p[0] / frozen.w) * 100} yPct={(p[1] / frozen.h) * 100} color={COLORS[i % COLORS.length]} label={i + 1} />
            ))}
            {draft && (
              <Marker
                xPct={(draft[0] / frozen.w) * 100}
                yPct={(draft[1] / frozen.h) * 100}
                color={COLORS[srcPoints.length % COLORS.length]}
                label={srcPoints.length + 1}
                pulse
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Marker({
  xPct,
  yPct,
  color,
  label,
  pulse,
  scale = 1,
}: {
  xPct: number;
  yPct: number;
  color: string;
  label: number;
  pulse?: boolean;
  scale?: number;
}) {
  return (
    <span
      className={`pointer-events-none absolute flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold text-white shadow ring-2 ring-white ${
        pulse ? 'animate-pulse' : ''
      }`}
      style={{
        left: `${xPct}%`,
        top: `${yPct}%`,
        backgroundColor: color,
        transform: `translate(-50%, -50%) scale(${1 / scale})`,
      }}
    >
      {label}
    </span>
  );
}

// ---- Live projection preview ---------------------------------------------- //

/**
 * Project live-tracked people's foot-points through the in-progress homography
 * onto the floor plan. This mirrors ingest exactly (both apply the homography to
 * raw source-pixel bboxes — ``tracks.consumer._project_foot``), so the dots land
 * where the analytics will place people: if a calibration is good they sit where
 * the people really are. Polls the shared track buffer ~2.5x/s (mounted app-wide
 * by ``useTrackEventStream``); no dots when there is no homography yet.
 */
function useLiveProjections(cameraId: string, H: number[] | null) {
  const [dots, setDots] = useState<{ key: string; x: number; y: number }[]>([]);
  useEffect(() => {
    if (!H) {
      setDots([]);
      return;
    }
    const tick = () => {
      const frame = getLatestFrame(cameraId);
      if (!frame) {
        setDots([]);
        return;
      }
      const out: { key: string; x: number; y: number }[] = [];
      for (const tr of frame.tracks) {
        const [fx, fy] = footPoint(tr.bbox);
        const p = projectPoint(H, fx, fy);
        if (p && p[0] >= 0 && p[0] <= 1 && p[1] >= 0 && p[1] <= 1) {
          out.push({ key: String(tr.track_id), x: p[0], y: p[1] });
        }
      }
      setDots(out);
    };
    tick();
    const id = window.setInterval(tick, 400);
    return () => window.clearInterval(id);
  }, [cameraId, H]);
  return dots;
}

function PreviewDot({ xPct, yPct, scale = 1 }: { xPct: number; yPct: number; scale?: number }) {
  return (
    <span
      className="pointer-events-none absolute h-3.5 w-3.5 rounded-full bg-emerald-500 ring-2 ring-white"
      style={{
        left: `${xPct}%`,
        top: `${yPct}%`,
        transform: `translate(-50%, -50%) scale(${1 / scale})`,
        boxShadow: '0 0 0 4px rgba(16,185,129,0.35)',
      }}
    />
  );
}

// ---- Main dialog ---------------------------------------------------------- //

export function CameraCalibrationDialog({
  camera,
  open,
  onOpenChange,
}: {
  camera: Camera;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const { data: plans, isLoading: plansLoading } = useFloorPlans(camera.site_id);
  const updateCamera = useUpdateCamera(camera.id);

  // Floor plans this camera is placed on (marker present) — the plane(s) its
  // homography can map into.
  const candidatePlans = useMemo(
    () => (plans ?? []).filter((p) => (p.markers ?? []).some((m) => m.camera_id === camera.id)),
    [plans, camera.id],
  );

  const [planId, setPlanId] = useState<string | null>(null);
  const [pairs, setPairs] = useState<Pair[]>([]);
  const [draftSrc, setDraftSrc] = useState<Pt | null>(null);
  const [imageRef, setImageRef] = useState<{ width: number; height: number } | null>(null);
  const [showPreview, setShowPreview] = useState(true);

  // Reset when reopened for a different camera / when candidates load.
  useEffect(() => {
    if (!open) return;
    setPairs([]);
    setDraftSrc(null);
    setImageRef(null);
    setPlanId(candidatePlans[0]?.id ?? null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, camera.id, candidatePlans.length]);

  const plan: FloorPlan | undefined = candidatePlans.find((p) => p.id === planId);

  function onCameraPoint(p: Pt, w: number, h: number) {
    setImageRef({ width: w, height: h });
    setDraftSrc(p);
  }
  function onFloorClick(fx: number, fy: number) {
    if (!draftSrc) {
      toast.message(t('cameras.calibration.needCameraFirst'));
      return;
    }
    setPairs((prev) => [...prev, { src: draftSrc, dst: [fx, fy] }]);
    setDraftSrc(null);
  }
  function undo() {
    if (draftSrc) {
      setDraftSrc(null);
    } else {
      setPairs((prev) => prev.slice(0, -1));
    }
  }

  // Reprojection error (mean/max), in % of the plan — a calibration quality signal.
  const quality = useMemo(() => {
    if (pairs.length < 4) return null;
    const H = solveHomography(pairs.slice(0, 4).map((p) => p.src), pairs.slice(0, 4).map((p) => p.dst));
    if (!H) return { ok: false, meanPct: 0, maxPct: 0, H: null as number[] | null };
    let sum = 0;
    let max = 0;
    for (const p of pairs) {
      const proj = projectPoint(H, p.src[0], p.src[1]);
      if (!proj) continue;
      const d = Math.hypot(proj[0] - p.dst[0], proj[1] - p.dst[1]);
      sum += d;
      max = Math.max(max, d);
    }
    return { ok: true, meanPct: (sum / pairs.length) * 100, maxPct: max * 100, H };
  }, [pairs]);

  // Live people projected through the in-progress homography onto the floor plan.
  const projections = useLiveProjections(
    camera.id,
    showPreview && quality?.ok ? quality.H : null,
  );

  async function save() {
    if (!plan || !imageRef) return;
    const H = quality?.H;
    if (!H) {
      toast.error(t('cameras.calibration.degenerate'));
      return;
    }
    const calibration: StoredCalibration = {
      floor_plan_id: plan.id,
      homography: H,
      image_ref: imageRef,
      src_points: pairs.map((p) => p.src),
      dst_points: pairs.map((p) => p.dst),
      calibrated_at: new Date().toISOString(),
    };
    try {
      await updateCamera.mutateAsync({ calibration: calibration as unknown as Record<string, unknown> });
      toast.success(t('cameras.calibration.saved'));
      onOpenChange(false);
    } catch {
      toast.error(t('cameras.calibration.saveFailed'));
    }
  }

  const existing = camera.calibration?.homography ? camera.calibration : null;

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('cameras.calibration.title', { name: camera.name })}
      description={t('cameras.calibration.subtitle')}
      size="xl"
      footer={
        <div className="flex w-full items-center justify-between gap-3">
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span>{t('cameras.calibration.pointsPlaced', { n: pairs.length })}</span>
            {quality?.ok && (
              <span className={quality.meanPct <= 2 ? 'text-success' : 'text-warning'}>
                {t('cameras.calibration.fitError', {
                  mean: quality.meanPct.toFixed(1),
                  max: quality.maxPct.toFixed(1),
                })}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={undo} disabled={pairs.length === 0 && !draftSrc}>
              <Undo2 className="mr-1 h-4 w-4" />
              {t('common.undo')}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setPairs([]);
                setDraftSrc(null);
              }}
              disabled={pairs.length === 0 && !draftSrc}
            >
              <Eraser className="mr-1 h-4 w-4" />
              {t('common.clear')}
            </Button>
            <Button
              variant="primary"
              onClick={save}
              disabled={pairs.length < 4 || !plan || !imageRef || !quality?.ok || updateCamera.isPending}
            >
              <Crosshair className="mr-1 h-4 w-4" />
              {t('cameras.calibration.save')}
            </Button>
          </div>
        </div>
      }
    >
      {plansLoading ? (
        <div className="flex h-40 items-center justify-center text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : candidatePlans.length === 0 ? (
        <div className="rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
          {t('cameras.calibration.noPlan')}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-muted-foreground">{t('cameras.calibration.instructions')}</p>
            <div className="flex items-center gap-2">
              {existing && (
                <span className="rounded-full bg-success/15 px-2 py-0.5 text-xs text-success">
                  {t('cameras.calibration.alreadyCalibrated')}
                </span>
              )}
              {candidatePlans.length > 1 && (
                <select
                  className="rounded-md border border-border bg-background px-2 py-1 text-sm"
                  value={planId ?? ''}
                  onChange={(e) => {
                    setPlanId(e.target.value);
                    setPairs([]);
                    setDraftSrc(null);
                  }}
                >
                  {candidatePlans.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <div className="h-[55vh]">
              <CameraCaptureSurface
                hlsUrl={camera.hls_url}
                srcPoints={pairs.map((p) => p.src)}
                draft={draftSrc}
                onPoint={onCameraPoint}
              />
            </div>
            <div className="flex h-[55vh] flex-col gap-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-muted-foreground">
                  {t('cameras.calibration.floorPlan')}
                </span>
                {quality?.ok && (
                  <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <input
                      type="checkbox"
                      checked={showPreview}
                      onChange={(e) => setShowPreview(e.target.checked)}
                    />
                    <span className="inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                    {t('cameras.calibration.livePreview')}
                    {showPreview && (
                      <span className="font-medium text-emerald-600">
                        {t('cameras.calibration.peopleProjected', { n: projections.length })}
                      </span>
                    )}
                  </label>
                )}
              </div>
              <div className="relative flex-1 overflow-hidden rounded-md border border-border">
                {plan && (
                  <FloorPlanViewer plan={plan} onPlaneClick={onFloorClick} showControls>
                    {({ currentScale }) => (
                      <>
                        {pairs.map((p, i) => (
                          <Marker
                            key={i}
                            xPct={p.dst[0] * 100}
                            yPct={p.dst[1] * 100}
                            color={COLORS[i % COLORS.length]}
                            label={i + 1}
                            scale={currentScale}
                          />
                        ))}
                        {showPreview &&
                          projections.map((d) => (
                            <PreviewDot
                              key={d.key}
                              xPct={d.x * 100}
                              yPct={d.y * 100}
                              scale={currentScale}
                            />
                          ))}
                      </>
                    )}
                  </FloorPlanViewer>
                )}
                {draftSrc && (
                  <div className="pointer-events-none absolute inset-x-0 top-0 z-10 bg-primary/90 px-2 py-1 text-center text-[11px] text-primary-foreground">
                    {t('cameras.calibration.nowClickFloor', { n: pairs.length + 1 })}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </Dialog>
  );
}
