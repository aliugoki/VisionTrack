import { useEffect, useRef } from 'react';
import { useSocket } from '@/shared/hooks/useSocket';
import type {
  BufferedFrame,
  TrackUpdateEvent,
  TrackLifecycleEvent,
} from '@/modules/tracks/types';

/**
 * Per-camera time-aligned event buffer.
 *
 * The overlay needs to answer "which boxes were detected at video
 * wall-clock time T?" — that requires holding recent events in memory
 * keyed by their frame_ts_ms.
 *
 * We keep a sorted array of BufferedFrames per camera, drop entries
 * older than BUFFER_RETENTION_MS, and expose getFrameNear() that
 * returns the closest-by-timestamp frame.
 *
 * Why not React state for the buffer?
 *   The buffer updates 10x/sec per camera. Re-rendering on every event
 *   would thrash. Instead we keep the buffer in a ref and have the
 *   canvas overlay read from it on every requestAnimationFrame.
 */

const BUFFER_RETENTION_MS = 30_000; // 30s — way more than HLS latency

// Module-level so multiple consumers of the same camera share state
const buffers: Map<string, BufferedFrame[]> = new Map();
const lifecycleListeners: Set<(e: TrackLifecycleEvent) => void> = new Set();

function pushFrame(cameraId: string, frame: BufferedFrame): void {
  const buf = buffers.get(cameraId) || [];
  // Insert maintaining ts_ms ascending order. Events arrive nearly
  // in-order but Socket.IO doesn't strictly guarantee that, so we
  // binary-search the insertion point.
  let lo = 0,
    hi = buf.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (buf[mid].ts_ms < frame.ts_ms) lo = mid + 1;
    else hi = mid;
  }
  buf.splice(lo, 0, frame);

  // Drop old entries
  const cutoff = Date.now() - BUFFER_RETENTION_MS;
  while (buf.length > 0 && buf[0].ts_ms < cutoff) buf.shift();

  buffers.set(cameraId, buf);
}

/**
 * Find the frame whose ts_ms is closest to `targetTsMs`.
 * Returns null if buffer is empty.
 *
 * Binary search; O(log n) per call. With a 30s buffer at 10 fps that's
 * 300 entries, log2(300) ≈ 9 — negligible per requestAnimationFrame.
 */
export function getFrameNear(
  cameraId: string,
  targetTsMs: number,
  maxDriftMs: number = 200
): BufferedFrame | null {
  const buf = buffers.get(cameraId);
  if (!buf || buf.length === 0) return null;

  // Binary search for the index where buf[i].ts_ms >= targetTsMs
  let lo = 0,
    hi = buf.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (buf[mid].ts_ms < targetTsMs) lo = mid + 1;
    else hi = mid;
  }

  // Candidates: buf[lo-1] (just before) and buf[lo] (at or after)
  const before = lo > 0 ? buf[lo - 1] : null;
  const after = lo < buf.length ? buf[lo] : null;

  let best: BufferedFrame | null = null;
  let bestDiff = Infinity;
  if (before) {
    const d = Math.abs(before.ts_ms - targetTsMs);
    if (d < bestDiff) {
      bestDiff = d;
      best = before;
    }
  }
  if (after) {
    const d = Math.abs(after.ts_ms - targetTsMs);
    if (d < bestDiff) {
      bestDiff = d;
      best = after;
    }
  }

  if (best === null || bestDiff > maxDriftMs) return null;
  return best;
}

/**
 * Subscribe to track + lifecycle events on the tenant socket and feed
 * them into the per-camera buffer.
 *
 * Mount this hook once at app level (in AppLayout, for example) so the
 * buffer fills up regardless of which page is showing. Camera page
 * components read from the buffer via getFrameNear().
 */
export function useTrackEventStream(
  onLifecycle?: (e: TrackLifecycleEvent) => void
): void {
  const { socket, connected } = useSocket();
  const lifecycleHandlerRef = useRef(onLifecycle);
  lifecycleHandlerRef.current = onLifecycle;

  useEffect(() => {
    if (!socket || !connected) return;

    const onTrackUpdate = (e: TrackUpdateEvent) => {
      pushFrame(e.camera_id, { ts_ms: e.frame_ts_ms, tracks: e.tracks });
    };
    const onLifecycleEvent = (e: TrackLifecycleEvent) => {
      // Broadcast to all listeners (camera page, alerts, etc.)
      for (const listener of lifecycleListeners) {
        try {
          listener(e);
        } catch (err) {
          // Don't let one buggy listener kill the rest
          console.error('lifecycle listener error', err);
        }
      }
      lifecycleHandlerRef.current?.(e);
    };

    socket.on('track_update', onTrackUpdate);
    socket.on('track_lifecycle', onLifecycleEvent);

    return () => {
      socket.off('track_update', onTrackUpdate);
      socket.off('track_lifecycle', onLifecycleEvent);
    };
  }, [socket, connected]);
}

/**
 * Get the most recent N points for a given camera + tracker_id, used
 * for drawing trails. Returns positions in source pixel space.
 */
export function getTrackTrail(
  cameraId: string,
  trackerId: number,
  maxAgeMs: number = 5_000
): { ts_ms: number; cx: number; cy: number }[] {
  const buf = buffers.get(cameraId);
  if (!buf) return [];
  const cutoff = Date.now() - maxAgeMs;
  const points: { ts_ms: number; cx: number; cy: number }[] = [];
  for (let i = buf.length - 1; i >= 0; i--) {
    const frame = buf[i];
    if (frame.ts_ms < cutoff) break;
    const track = frame.tracks.find((t) => t.track_id === trackerId);
    if (track) {
      const [x1, y1, x2, y2] = track.bbox;
      points.push({
        ts_ms: frame.ts_ms,
        cx: (x1 + x2) / 2,
        cy: (y1 + y2) / 2,
      });
    }
  }
  return points.reverse();
}


/**
 * Get the most recent frame for a camera. Used by widgets that want
 * a "right now" snapshot — e.g. a live count badge on the camera card.
 * Cheaper than computing trails; just reads the tail of the buffer.
 */
export function getLatestFrame(cameraId: string): BufferedFrame | null {
  const buf = buffers.get(cameraId);
  if (!buf || buf.length === 0) return null;
  return buf[buf.length - 1];
}

/**
 * Subscribe to lifecycle events globally — distinct from
 * useTrackEventStream which mounts the WebSocket. Use this in
 * components that just want to react to track started/ended events.
 */
export function subscribeToLifecycle(
  listener: (e: TrackLifecycleEvent) => void
): () => void {
  lifecycleListeners.add(listener);
  return () => lifecycleListeners.delete(listener) as unknown as void;
}
