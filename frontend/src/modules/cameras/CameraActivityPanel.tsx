import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Activity, User, ChevronRight } from 'lucide-react';
import { Badge } from '@/shared/components/Badge';
import { useActiveTracksByCamera } from '@/modules/tracks/api';
import { getLatestFrame } from '@/modules/tracks/useTrackEvents';

const LIVE_COUNT_REFRESH_MS = 1_000;
const MAX_RECENT_TRACKS = 3;

/**
 * Per-camera activity footer.
 *
 * Two data sources, deliberately:
 *
 *   - Live count badge: pulls from the in-memory Socket.IO buffer
 *     (getLatestFrame). Sub-second freshness, no API calls.
 *
 *   - Recent tracks list: pulls from /tracks/active via polling. Slower
 *     but shows the canonical tracker_id assignments and (eventually)
 *     person_id attributions from the matcher.
 *
 * If a track has been attributed to a person, the row links to
 * /persons/:personId. Otherwise it's a plain (non-linked) row showing
 * the tracker_id.
 */
export function CameraActivityPanel({
  cameraId,
  online,
}: {
  cameraId: string;
  online: boolean;
}) {
  const { t } = useTranslation();

  // Tick to re-read the Socket.IO buffer (which lives outside React state)
  const [, forceTick] = useState(0);
  useEffect(() => {
    if (!online) return;
    const interval = window.setInterval(
      () => forceTick((n) => n + 1),
      LIVE_COUNT_REFRESH_MS
    );
    return () => window.clearInterval(interval);
  }, [online]);

  const latest = online ? getLatestFrame(cameraId) : null;
  // Consider the frame "live" only if within the last 3s — otherwise the
  // stream has gone quiet and showing a stale count would mislead.
  const isLiveFresh = latest
    ? Date.now() - latest.ts_ms < 3_000
    : false;
  const liveCount = isLiveFresh && latest ? latest.tracks.length : 0;

  const { data: activeTracks } = useActiveTracksByCamera(
    online ? cameraId : undefined
  );

  const recent = useMemo(() => {
    if (!activeTracks) return [];
    // Most recent first; cap at MAX_RECENT_TRACKS
    return [...activeTracks]
      .sort((a, b) => b.started_at.localeCompare(a.started_at))
      .slice(0, MAX_RECENT_TRACKS);
  }, [activeTracks]);

  return (
    <div className="border-t border-border bg-muted/20 px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs">
          <Activity
            className={
              isLiveFresh
                ? 'h-3.5 w-3.5 text-success'
                : 'h-3.5 w-3.5 text-muted-foreground'
            }
          />
          <span className="font-medium text-foreground">
            {t('cameras.activity.liveCount', { count: liveCount })}
          </span>
          {!isLiveFresh && online && (
            <span className="text-muted-foreground">
              · {t('cameras.activity.idle')}
            </span>
          )}
        </div>
        <Link
          to={`/persons?camera=${cameraId}`}
          className="inline-flex items-center text-xs text-primary hover:underline"
        >
          {t('cameras.activity.viewPersons')}
          <ChevronRight className="h-3.5 w-3.5 ms-0.5 rtl:rotate-180" />
        </Link>
      </div>

      {recent.length > 0 && (
        <ul className="mt-2 space-y-1">
          {recent.map((track) => {
            const personId = track.person_id;
            const inner = (
              <>
                <User className="h-3 w-3 shrink-0" />
                <span className="font-mono text-[11px]">
                  #{track.tracker_id}
                </span>
                {personId ? (
                  <span className="ms-auto text-[11px] text-primary">
                    {t('cameras.activity.identified')}
                  </span>
                ) : (
                  <Badge tone="neutral" className="ms-auto">
                    <span className="text-[10px]">
                      {t('cameras.activity.unidentified')}
                    </span>
                  </Badge>
                )}
              </>
            );
            return (
              <li key={track.id}>
                {personId ? (
                  <Link
                    to={`/persons/${personId}`}
                    className="flex items-center gap-2 rounded px-1.5 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    {inner}
                  </Link>
                ) : (
                  <div className="flex items-center gap-2 px-1.5 py-1 text-xs text-muted-foreground">
                    {inner}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
