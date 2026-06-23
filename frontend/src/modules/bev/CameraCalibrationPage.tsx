import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Hls from 'hls.js';
import { Crosshair, RotateCcw, Save } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/shared/components/Button';
import { Card } from '@/shared/components/Card';
import { Select, type SelectOption } from '@/shared/components/Select';
import { Spinner } from '@/shared/components/Spinner';
import { Badge } from '@/shared/components/Badge';
import { useAuth } from '@/shared/hooks/useAuth';
import { CAMERA_CALIBRATE } from '@/shared/lib/permissions';
import { useCameras } from '@/modules/cameras/api';
import { useFloorPlans } from '@/modules/floor-plan/api';
import { FloorPlanViewer } from '@/modules/floor-plan/FloorPlanViewer';
import { useSetCameraCalibration } from '@/modules/bev/api';
import { readCalibration, solveHomography, type Point } from '@/modules/bev/homography';

/** Same MediaMTX→/hls proxy normalization the live player uses. */
function normalizeHlsUrl(url: string): string {
  try {
    const parsed = new URL(url, window.location.origin);
    return `/hls${parsed.pathname}`;
  } catch {
    return url;
  }
}

const DOT_COLORS = ['#2E9456', '#2563eb', '#d97706', '#dc2626'];

/** Self-contained HLS video with a click-capture overlay. Reports clicks in
 *  SOURCE-PIXEL coordinates (the space track bboxes live in) using the
 *  video's natural resolution, and reports that resolution upward. */
function CalibVideo({
  hlsUrl,
  points,
  onPick,
  onNatural,
}: {
  hlsUrl: string;
  points: Point[]; // normalized 0..1 for display
  onPick: (srcPx: Point, normalized: Point) => void;
  onNatural: (w: number, h: number) => void;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const natural = useRef<{ w: number; h: number } | null>(null);
  // Hold the latest onNatural without making it an effect dependency — otherwise
  // every parent re-render (e.g. clicking a point) would tear down and rebuild
  // the HLS instance, causing the video to flicker/reload.
  const onNaturalRef = useRef(onNatural);
  onNaturalRef.current = onNatural;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    natural.current = null; // re-detect resolution for this stream
    const url = normalizeHlsUrl(hlsUrl);
    let hls: Hls | null = null;
    const onMeta = () => {
      if (natural.current) return; // resolution is fixed; set it once
      if (video.videoWidth && video.videoHeight) {
        natural.current = { w: video.videoWidth, h: video.videoHeight };
        onNaturalRef.current(video.videoWidth, video.videoHeight);
      }
    };
    video.addEventListener('loadedmetadata', onMeta);
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = url; // Safari native HLS
    } else if (Hls.isSupported()) {
      hls = new Hls({ lowLatencyMode: true });
      hls.attachMedia(video);
      hls.on(Hls.Events.MEDIA_ATTACHED, () => hls!.loadSource(url));
    }
    return () => {
      video.removeEventListener('loadedmetadata', onMeta);
      if (hls) hls.destroy();
    };
    // Only rebuild the player when the stream URL changes — NOT on every render.
  }, [hlsUrl]);

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const nx = (e.clientX - rect.left) / rect.width;
    const ny = (e.clientY - rect.top) / rect.height;
    const nat = natural.current;
    if (!nat) {
      toast.error('Video not ready yet');
      return;
    }
    onPick([nx * nat.w, ny * nat.h], [nx, ny]);
  };

  return (
    <div className="relative w-full overflow-hidden rounded-md bg-black">
      <video ref={videoRef} autoPlay muted playsInline className="block w-full" />
      <div className="absolute inset-0 cursor-crosshair" onClick={handleClick}>
        {points.map((p, i) => (
          <div
            key={i}
            className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white"
            style={{
              left: `${p[0] * 100}%`,
              top: `${p[1] * 100}%`,
              width: 16,
              height: 16,
              background: DOT_COLORS[i % DOT_COLORS.length],
            }}
          >
            <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-[10px] font-bold text-white">
              {i + 1}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function CameraCalibrationPage() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canCalibrate = hasPermission(CAMERA_CALIBRATE);

  const { data: cameras, isLoading: camsLoading } = useCameras();
  const [cameraId, setCameraId] = useState<string>('');
  const camera = useMemo(
    () => cameras?.find((c) => c.id === cameraId),
    [cameras, cameraId]
  );

  const { data: plans } = useFloorPlans(camera?.site_id);
  const [planId, setPlanId] = useState<string>('');
  const plan = useMemo(() => plans?.find((p) => p.id === planId), [plans, planId]);

  const [srcNorm, setSrcNorm] = useState<Point[]>([]); // for video display (0..1)
  const [srcPx, setSrcPx] = useState<Point[]>([]); // source-pixel correspondences
  const [dst, setDst] = useState<Point[]>([]); // floor-plan fractional
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);

  const save = useSetCameraCalibration(cameraId);

  // Pre-fill from existing calibration when switching camera.
  useEffect(() => {
    setSrcNorm([]);
    setSrcPx([]);
    setDst([]);
    setNatural(null);
    const cal = readCalibration(camera?.calibration);
    if (cal) setPlanId(cal.floor_plan_id);
    else setPlanId('');
  }, [cameraId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!canCalibrate) {
    return (
      <Card className="p-8 text-center text-muted-foreground">
        {t('bev.noCalibratePermission')}
      </Card>
    );
  }

  const cameraOptions: SelectOption[] = (cameras ?? []).map((c) => ({
    value: c.id,
    label: readCalibration(c.calibration) ? `${c.name} ✓` : c.name,
  }));
  const planOptions: SelectOption[] = (plans ?? []).map((p) => ({
    value: p.id,
    label: p.name,
  }));

  const ready = srcPx.length >= 4 && dst.length >= 4 && !!natural && !!planId;

  const onPickVideo = (px: Point, norm: Point) => {
    if (srcPx.length >= 4) return;
    setSrcPx((s) => [...s, px]);
    setSrcNorm((s) => [...s, norm]);
  };
  const onPickPlan = (x: number, y: number) => {
    if (dst.length >= 4) return;
    setDst((d) => [...d, [x, y]]);
  };
  const reset = () => {
    setSrcNorm([]);
    setSrcPx([]);
    setDst([]);
  };

  const onSave = async () => {
    const H = solveHomography(srcPx.slice(0, 4), dst.slice(0, 4));
    if (!H) {
      toast.error(t('bev.degeneratePoints'));
      return;
    }
    try {
      await save.mutateAsync({
        floor_plan_id: planId,
        homography: H,
        image_ref: { width: natural!.w, height: natural!.h },
        src_points: srcPx,
        dst_points: dst,
      });
      toast.success(t('bev.calibrationSaved'));
    } catch {
      toast.error(t('bev.calibrationFailed'));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-foreground">
            <Crosshair className="h-6 w-6" />
            {t('bev.calibrationTitle')}
          </h1>
          <p className="text-sm text-muted-foreground">{t('bev.calibrationSubtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={reset} disabled={!srcPx.length && !dst.length}>
            <RotateCcw className="me-1 h-4 w-4" />
            {t('bev.reset')}
          </Button>
          <Button onClick={onSave} disabled={!ready || save.isPending}>
            {save.isPending ? <Spinner size={16} /> : <Save className="me-1 h-4 w-4" />}
            {t('bev.saveCalibration')}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Select
          label={t('bev.camera')}
          options={cameraOptions}
          placeholder={camsLoading ? t('common.loading') : t('bev.selectCamera')}
          value={cameraId}
          onChange={(e) => setCameraId(e.target.value)}
        />
        <Select
          label={t('bev.floorPlan')}
          options={planOptions}
          placeholder={t('bev.selectFloorPlan')}
          value={planId}
          onChange={(e) => setPlanId(e.target.value)}
        />
      </div>

      <p className="text-sm text-muted-foreground">
        {t('bev.calibrationHint', { srcCount: srcPx.length, dstCount: dst.length })}
      </p>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card className="p-2">
          <div className="mb-2 flex items-center justify-between px-1">
            <span className="text-sm font-medium">{t('bev.cameraView')}</span>
            <Badge tone={srcPx.length >= 4 ? 'success' : 'neutral'}>{srcPx.length}/4</Badge>
          </div>
          {camera ? (
            <CalibVideo
              hlsUrl={camera.hls_url}
              points={srcNorm}
              onPick={onPickVideo}
              onNatural={(w, h) => setNatural({ w, h })}
            />
          ) : (
            <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
              {t('bev.selectCamera')}
            </div>
          )}
        </Card>

        <Card className="p-2">
          <div className="mb-2 flex items-center justify-between px-1">
            <span className="text-sm font-medium">{t('bev.floorPlanView')}</span>
            <Badge tone={dst.length >= 4 ? 'success' : 'neutral'}>{dst.length}/4</Badge>
          </div>
          {plan ? (
            <div className="h-[360px]">
              <FloorPlanViewer plan={plan} onPlaneClick={onPickPlan}>
                {() => (
                  <>
                    {dst.map((p, i) => (
                      <div
                        key={i}
                        className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white"
                        style={{
                          left: p[0] * plan.width_px,
                          top: p[1] * plan.height_px,
                          width: 18,
                          height: 18,
                          background: DOT_COLORS[i % DOT_COLORS.length],
                        }}
                      >
                        <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 text-[10px] font-bold text-white">
                          {i + 1}
                        </span>
                      </div>
                    ))}
                  </>
                )}
              </FloorPlanViewer>
            </div>
          ) : (
            <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
              {t('bev.selectFloorPlan')}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
