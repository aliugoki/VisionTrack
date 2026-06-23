import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Film, Loader2 } from 'lucide-react';
import { Button } from '@/shared/components/Button';
import { useCameras } from '@/modules/cameras/api';
import { useClipForAlert } from '@/modules/recordings/api';
import { PlaybackModal } from '@/modules/recordings/RecordingsPage';
import { toast } from 'sonner';

/**
 * Per-alert "View clip" affordance for the AlertsPage.
 *
 * Behavior:
 *   - On mount: lazy hook is NOT enabled — we don't pre-fetch every clip
 *     for every alert in the list (would hammer the backend).
 *   - On button click: trigger the fetch, then open the playback modal
 *     at the right offset.
 *   - 404 response (no clip available): show a toast, keep button enabled
 *     for retry.
 *
 * Why a small standalone component instead of inlining in AlertsPage:
 *   The component owns its own modal state. Inlining would require
 *   AlertsPage to track per-row modal state which gets messy with
 *   60+ rows. Per-row component scopes state to the row's lifetime.
 */
export function AlertClipButton({ alertId }: { alertId: string }) {
  const { t } = useTranslation();
  const { data: cameras = [] } = useCameras();
  // Two flags: `requested` triggers the fetch; `open` opens the modal
  // once data arrives. Separating them lets us show the loader on the
  // button while the request is in-flight.
  const [requested, setRequested] = useState(false);
  const [open, setOpen] = useState(false);

  const { data: clip, isLoading, isError } = useClipForAlert(
    requested ? alertId : null
  );

  // When the fetch completes (success), pop the modal
  if (requested && !isLoading && clip && !open) {
    setOpen(true);
  }
  // When the fetch completes (no clip available — 404), surface toast
  // and reset so the user can try again later if recordings appear.
  if (requested && !isLoading && clip === null) {
    toast.info(t('alerts.clip.unavailable'));
    setRequested(false);
  }
  if (requested && isError) {
    toast.error(t('alerts.clip.error'));
    setRequested(false);
  }

  const camera = clip
    ? cameras.find((c) => c.id === clip.recording.camera_id)
    : null;

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        disabled={isLoading}
        onClick={(e) => {
          e.stopPropagation();
          setRequested(true);
        }}
      >
        {isLoading ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          <Film className="h-3 w-3" />
        )}
        {t('alerts.clip.view')}
      </Button>

      {open && clip && camera && (
        <PlaybackModal
          recording={clip.recording}
          cameraName={camera.name}
          cameraMediamtxPath={camera.mediamtx_path}
          cameraCodec={camera.codec}
          initialOffsetSeconds={clip.offset_seconds}
          onClose={() => {
            setOpen(false);
            setRequested(false);
          }}
        />
      )}
    </>
  );
}
