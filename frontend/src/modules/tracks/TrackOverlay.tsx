import { useEffect, useRef, useState } from 'react';
import { getFrameNear, getTrackTrail } from '@/modules/tracks/useTrackEvents';
import type { TrackBox } from '@/modules/tracks/types';

/**
 * Bounding box overlay drawn on a <canvas> positioned absolutely over
 * the HLS <video>. The canvas matches the video's displayed size, and
 * track box coordinates (which are in source pixel space) are scaled
 * to canvas space using the source-vs-display dimension ratio.
 *
 * Time alignment:
 *   The video shows frames from ~6-14s in the past (HLS segment buffer).
 *   We extract the wall-clock time of the currently displayed frame from
 *   the HLS PROGRAM-DATE-TIME tag (via hls.js' fragment metadata), then
 *   look up the matching event from our buffer.
 *
 * If we can't determine the video wall-clock, we fall back to drawing
 * the most recent event minus an estimated HLS latency.
 */

// Distinct colors for tracker IDs. Modulo into this palette.
// Chosen for readability on dark video backgrounds + colorblind-friendly.
const TRACK_COLORS = [
  '#10b981', // emerald
  '#3b82f6', // blue
  '#f59e0b', // amber
  '#ec4899', // pink
  '#8b5cf6', // violet
  '#06b6d4', // cyan
  '#84cc16', // lime
  '#f97316', // orange
];

function colorFor(trackerId: number): string {
  return TRACK_COLORS[trackerId % TRACK_COLORS.length];
}

export interface OverlayOptions {
  enabled: boolean;
  showLabels: boolean;
  showTrails: boolean;
}

interface TrackOverlayProps {
  cameraId: string;
  /** Reference to the underlying <video> element. */
  videoRef: React.RefObject<HTMLVideoElement | null>;
  /**
   * Reference to the hls.js instance, used to read PROGRAM-DATE-TIME from
   * fragment metadata. Optional — if absent we fall back to a fixed lag.
   */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  hlsRef: React.RefObject<any>;
  options: OverlayOptions;
}

export function TrackOverlay({
  cameraId,
  videoRef,
  hlsRef,
  options,
}: TrackOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef<number>();
  const [sourceSize, setSourceSize] = useState<{
    w: number;
    h: number;
  } | null>(null);

  // Pick up the source video dimensions once metadata loads.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onMetadata = () => {
      if (video.videoWidth > 0 && video.videoHeight > 0) {
        setSourceSize({ w: video.videoWidth, h: video.videoHeight });
      }
    };
    onMetadata();
    video.addEventListener('loadedmetadata', onMetadata);
    video.addEventListener('resize', onMetadata);
    return () => {
      video.removeEventListener('loadedmetadata', onMetadata);
      video.removeEventListener('resize', onMetadata);
    };
  }, [videoRef]);

  // Main draw loop: 60 fps requestAnimationFrame; pulls latest aligned
  // event from buffer and renders boxes.
  useEffect(() => {
    if (!options.enabled) {
      // Clear the canvas and stop the loop
      const canvas = canvasRef.current;
      if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx?.clearRect(0, 0, canvas.width, canvas.height);
      }
      return;
    }

    let stopped = false;

    const tick = () => {
      if (stopped) return;
      drawOneFrame({
        canvas: canvasRef.current,
        video: videoRef.current,
        hls: hlsRef.current,
        sourceSize,
        cameraId,
        options,
      });
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);

    return () => {
      stopped = true;
      if (rafRef.current !== undefined) cancelAnimationFrame(rafRef.current);
    };
  }, [cameraId, sourceSize, options, videoRef, hlsRef]);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 h-full w-full"
      style={{ display: options.enabled ? 'block' : 'none' }}
    />
  );
}

// ----------------------------------------------------------------------------
// Drawing logic — pulled out of the component so it stays out of React's
// re-render cycle. This is called from requestAnimationFrame.

interface DrawFrameArgs {
  canvas: HTMLCanvasElement | null;
  video: HTMLVideoElement | null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  hls: any;
  sourceSize: { w: number; h: number } | null;
  cameraId: string;
  options: OverlayOptions;
}

function drawOneFrame({
  canvas,
  video,
  hls,
  sourceSize,
  cameraId,
  options,
}: DrawFrameArgs) {
  if (!canvas || !video || !sourceSize) return;

  // Match canvas internal resolution to its display size, accounting for
  // device pixel ratio so lines stay crisp on HiDPI screens.
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const dispW = rect.width;
  const dispH = rect.height;
  if (dispW === 0 || dispH === 0) return;

  const targetW = Math.round(dispW * dpr);
  const targetH = Math.round(dispH * dpr);
  if (canvas.width !== targetW) canvas.width = targetW;
  if (canvas.height !== targetH) canvas.height = targetH;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, dispW, dispH);

  // Determine what wall-clock time the currently-playing video frame
  // corresponds to. PROGRAM-DATE-TIME is the right way; we use it when
  // available and fall back to a fixed estimated latency otherwise.
  const targetTsMs = currentVideoWallClockMs(video, hls);
  if (targetTsMs === null) return;

  const frame = getFrameNear(cameraId, targetTsMs);
  if (!frame) return;

  // Account for object-fit:contain letterboxing — the displayed video
  // may have black bars top/bottom or left/right depending on the
  // source aspect ratio vs the canvas aspect ratio.
  const sourceAR = sourceSize.w / sourceSize.h;
  const dispAR = dispW / dispH;
  let videoW: number, videoH: number, offsetX = 0, offsetY = 0;
  if (sourceAR > dispAR) {
    // Source is wider than display → letterbox top/bottom
    videoW = dispW;
    videoH = dispW / sourceAR;
    offsetY = (dispH - videoH) / 2;
  } else {
    // Source is taller than display → pillarbox left/right
    videoH = dispH;
    videoW = dispH * sourceAR;
    offsetX = (dispW - videoW) / 2;
  }
  const sx = videoW / sourceSize.w;
  const sy = videoH / sourceSize.h;

  // Draw each box
  ctx.lineWidth = 2;
  ctx.font = '500 12px system-ui, sans-serif';
  ctx.textBaseline = 'top';

  for (const track of frame.tracks) {
    drawBox(ctx, track, sx, sy, offsetX, offsetY, options);

    if (options.showTrails) {
      drawTrail(ctx, cameraId, track, sx, sy, offsetX, offsetY);
    }
  }
}

function drawBox(
  ctx: CanvasRenderingContext2D,
  track: TrackBox,
  sx: number,
  sy: number,
  offsetX: number,
  offsetY: number,
  options: OverlayOptions
) {
  const color = colorFor(track.track_id);
  const [x1, y1, x2, y2] = track.bbox;
  const dx = offsetX + x1 * sx;
  const dy = offsetY + y1 * sy;
  const dw = (x2 - x1) * sx;
  const dh = (y2 - y1) * sy;

  ctx.strokeStyle = color;
  ctx.strokeRect(dx, dy, dw, dh);

  if (options.showLabels) {
    const label = `#${track.track_id} ${Math.round(track.confidence * 100)}%`;
    const metrics = ctx.measureText(label);
    const padding = 4;
    const labelW = metrics.width + padding * 2;
    const labelH = 16;

    ctx.fillStyle = color;
    ctx.fillRect(dx, dy - labelH, labelW, labelH);

    ctx.fillStyle = '#000';
    ctx.fillText(label, dx + padding, dy - labelH + 2);
  }
}

function drawTrail(
  ctx: CanvasRenderingContext2D,
  cameraId: string,
  track: TrackBox,
  sx: number,
  sy: number,
  offsetX: number,
  offsetY: number
) {
  const trail = getTrackTrail(cameraId, track.track_id, 5_000);
  if (trail.length < 2) return;

  const color = colorFor(track.track_id);
  const now = Date.now();

  ctx.lineWidth = 2;
  ctx.lineCap = 'round';
  for (let i = 1; i < trail.length; i++) {
    const a = trail[i - 1];
    const b = trail[i];
    const age = now - b.ts_ms;
    const alpha = Math.max(0, 1 - age / 5_000);
    ctx.strokeStyle = withAlpha(color, alpha);
    ctx.beginPath();
    ctx.moveTo(offsetX + a.cx * sx, offsetY + a.cy * sy);
    ctx.lineTo(offsetX + b.cx * sx, offsetY + b.cy * sy);
    ctx.stroke();
  }
}

function withAlpha(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// ----------------------------------------------------------------------------
// Time alignment helpers

/**
 * Return the wall-clock millis corresponding to the currently-displayed
 * video frame.
 *
 * Uses hls.js' fragment program-date-time when available. The
 * fragments[] array exposes each segment's PROGRAM-DATE-TIME tag from
 * the HLS manifest — MediaMTX emits these by default. We find which
 * fragment contains video.currentTime, then add the offset within that
 * fragment to its programDateTime.
 *
 * Returns null if alignment isn't possible (e.g. no PDT tags, no
 * fragments loaded). Caller should skip drawing rather than guess.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function currentVideoWallClockMs(video: HTMLVideoElement, hls: any): number | null {
  if (!video || video.readyState < 2) return null;
  const currentTime = video.currentTime;

  // hls.js exposes levelDetails on the live level
  const level = hls?.levels?.[hls.currentLevel];
  const details = level?.details;
  const fragments = details?.fragments;
  if (!fragments || fragments.length === 0) {
    // Fallback: assume a fixed lag behind real time
    return Date.now() - 6000;
  }

  // Find the fragment containing currentTime
  for (const frag of fragments) {
    if (
      currentTime >= frag.start &&
      currentTime < frag.start + frag.duration
    ) {
      const pdt = frag.programDateTime;
      if (typeof pdt === 'number') {
        const offsetWithinFrag = currentTime - frag.start;
        return pdt + offsetWithinFrag * 1000;
      }
    }
  }

  // Outside of any fragment — use the last one's PDT as best-effort
  const lastFrag = fragments[fragments.length - 1];
  if (typeof lastFrag.programDateTime === 'number') {
    return lastFrag.programDateTime + lastFrag.duration * 1000;
  }

  return Date.now() - 6000;
}
