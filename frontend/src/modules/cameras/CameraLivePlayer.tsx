import { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';
import { AlertCircle, Loader2 } from 'lucide-react';
import { cn } from '@/shared/lib/cn';
import {
  TrackOverlay,
  type OverlayOptions,
} from '@/modules/tracks/TrackOverlay';
import { OverlayControls } from '@/modules/tracks/OverlayControls';

interface CameraLivePlayerProps {
  /** Browser-relative HLS URL (e.g. "/hls/cam-abc-h264/index.m3u8"). */
  hlsUrl: string;
  /** Path label shown in the error overlay (cosmetic only). */
  label?: string;
  /**
   * Camera UUID. When provided, enables the bounding-box overlay subscribed
   * to Socket.IO track events for this camera.
   */
  cameraId?: string;
  /**
   * Initial overlay state. The full preview dialog defaults to overlay-on +
   * labels off + trails off; live wall tiles also default to overlay-on +
   * labels/trails off (small tiles can't show readable labels). Caller can
   * override per context.
   */
  overlayDefaults?: Partial<OverlayOptions>;
  /** When true, hide the OverlayControls UI (only the boxes themselves render). */
  hideOverlayControls?: boolean;
  className?: string;
  muted?: boolean;
  autoPlay?: boolean;
  /** When true, show a low-key spinner overlay rather than full status text. */
  compact?: boolean;
}

type PlayerState = 'loading' | 'playing' | 'error';

/**
 * Convert a server-supplied HLS URL into a browser-relative one.
 *
 * The backend returns hls_url like "http://mediamtx:8888/cam-xxx/index.m3u8"
 * because that's reachable inside the Docker network. The browser sees
 * `mediamtx` as a non-resolvable hostname, so we strip the scheme+host
 * and let Vite's /hls proxy entry route the request to MediaMTX.
 */
function normalizeHlsUrl(url: string): string {
  // Already relative — use as-is
  if (url.startsWith('/')) return url;
  try {
    const parsed = new URL(url);
    return `/hls${parsed.pathname}`;
  } catch {
    return url;
  }
}

export function CameraLivePlayer({
  hlsUrl,
  label,
  cameraId,
  overlayDefaults,
  hideOverlayControls = false,
  className,
  muted = true,
  autoPlay = true,
  compact = false,
}: CameraLivePlayerProps) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const hlsRef = useRef<Hls | null>(null);
  const [state, setState] = useState<PlayerState>('loading');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Overlay options. Defaults to overlay-on but no labels/trails — clean
  // initial look that still proves the AI is working. Callers can override
  // via overlayDefaults (e.g. Live Wall tiles disable labels by default
  // since text isn't readable at 480x270).
  const [overlayOptions, setOverlayOptions] = useState<OverlayOptions>({
    enabled: true,
    showLabels: false,
    showTrails: false,
    ...overlayDefaults,
  });

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    // Defensive: Chrome's autoplay policy checks the muted HTML attribute,
    // not the JavaScript property. React's `muted` prop only sets the
    // property — we set both here and use `defaultMuted` in markup so
    // Chrome sees the video as muted at the moment of the autoplay check.
    // Without this, Chrome silently blocks autoplay while Firefox plays.
    if (muted) {
      video.muted = true;
      video.setAttribute('muted', '');
    }
    video.playsInline = true;

    const url = normalizeHlsUrl(hlsUrl);
    setState('loading');
    setErrorMsg(null);

    // Safari has native HLS — skip hls.js
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = url;
      const onPlaying = () => setState('playing');
      const onError = () => {
        setState('error');
        setErrorMsg('Stream unavailable');
      };
      video.addEventListener('playing', onPlaying);
      video.addEventListener('error', onError);
      return () => {
        video.removeEventListener('playing', onPlaying);
        video.removeEventListener('error', onError);
        video.removeAttribute('src');
        video.load();
      };
    }

    if (!Hls.isSupported()) {
      setState('error');
      setErrorMsg('HLS not supported in this browser');
      return;
    }

    const hls = new Hls({
      // Low-latency-friendly defaults. MediaMTX HLS segments are ~2s,
      // so a live edge tolerance of 3s keeps playback near real-time
      // without thrashing under jitter.
      liveSyncDuration: 3,
      liveMaxLatencyDuration: 10,
      enableWorker: true,
      // Retry the manifest aggressively — when MediaMTX is still pulling
      // the RTSP source on first connect it can 404 for a few seconds.
      manifestLoadingMaxRetry: 8,
      manifestLoadingRetryDelay: 1000,
      manifestLoadingMaxRetryTimeout: 16000,
    });
    hlsRef.current = hls;

    hls.attachMedia(video);
    hls.on(Hls.Events.MEDIA_ATTACHED, () => {
      hls.loadSource(url);
    });

    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      setState('playing');
      if (autoPlay) {
        void video.play().catch(() => {
          // Autoplay blocked — leave on the user to click play. Not an error.
        });
      }
    });

    hls.on(Hls.Events.ERROR, (_event, data) => {
      if (!data.fatal) return;
      switch (data.type) {
        case Hls.ErrorTypes.NETWORK_ERROR:
          // Network error — retry from the manifest
          hls.startLoad();
          break;
        case Hls.ErrorTypes.MEDIA_ERROR:
          // Try to recover from a media error (decoding issue)
          hls.recoverMediaError();
          break;
        default:
          setState('error');
          setErrorMsg(data.details || 'Stream error');
          hls.destroy();
          hlsRef.current = null;
      }
    });

    return () => {
      if (hlsRef.current) {
        hlsRef.current.destroy();
        hlsRef.current = null;
      }
    };
  }, [hlsUrl, autoPlay, muted]);

  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-md bg-black',
        className
      )}
    >
      <video
        ref={videoRef}
        className="h-full w-full object-contain"
        muted={muted}
        playsInline
        controls={!compact}
      />

      {/* Track overlay — only when camera id provided AND stream is playing.
          The overlay is positioned absolutely on top of the video and
          subscribes to Socket.IO events for this specific camera. */}
      {cameraId && state === 'playing' && (
        <>
          <TrackOverlay
            cameraId={cameraId}
            videoRef={videoRef}
            hlsRef={hlsRef}
            options={overlayOptions}
          />
          {!compact && !hideOverlayControls && (
            <OverlayControls
              options={overlayOptions}
              onChange={setOverlayOptions}
            />
          )}
        </>
      )}

      {state === 'loading' && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/40">
          <div className="flex flex-col items-center gap-2 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin" />
            {!compact && <span className="text-xs">Connecting to stream...</span>}
          </div>
        </div>
      )}

      {state === 'error' && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/60">
          <div className="flex flex-col items-center gap-2 px-4 text-center">
            <AlertCircle className="h-6 w-6 text-danger" />
            <span className="text-xs font-medium text-foreground">
              {errorMsg || 'Stream unavailable'}
            </span>
            {!compact && label && (
              <span className="font-mono text-[10px] text-muted-foreground">
                {label}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
