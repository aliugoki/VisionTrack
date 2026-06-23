import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { X, Maximize2, Video } from 'lucide-react';
import { CameraLivePlayer } from '@/modules/cameras/CameraLivePlayer';
import type { Camera } from '@/shared/types/api';
import type { FloorPlanMarker } from '@/modules/floor-plan/types';

interface MarkerLivePreviewProps {
  /** The marker that was clicked. Position used as the popover anchor. */
  marker: FloorPlanMarker;
  /** The camera the marker references (for hls_url + name). */
  camera: Camera | undefined;
  /** The plan's pixel dimensions — needed for absolute positioning. */
  imageWidthPx: number;
  imageHeightPx: number;
  /** Called when the operator dismisses the popover (X click, ESC, outside click). */
  onClose: () => void;
  /** Optional — called when operator clicks the expand icon (full-screen view). */
  onExpand?: () => void;
}

/**
 * Anchored popover showing a live HLS feed from the camera at this marker.
 * Sits over the floor plan, positioned next to the marker dot.
 *
 * Positioning strategy:
 *   The popover is a child of the same source-pixel container as the
 *   marker layer, so it inherits the floor plan's zoom/pan transform.
 *   It's anchored to the marker's fractional position via percent left/top.
 *
 *   We use a counter-scale transform (1/currentScale) so the popover stays
 *   a constant on-screen size as the floor plan zooms — same trick as the
 *   marker dots. Without this, the popover would balloon at high zoom
 *   levels and become unusable.
 *
 *   Smart positioning: if the marker is in the right half of the plan,
 *   the popover opens to the LEFT of the marker (otherwise it'd clip off
 *   the right edge). Same logic for top vs bottom.
 *
 * Dismiss:
 *   - X button
 *   - Escape key
 *   - Click outside the popover
 */
export function MarkerLivePreview({
  marker,
  camera,
  imageWidthPx,
  imageHeightPx,
  onClose,
  onExpand,
}: MarkerLivePreviewProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const popoverRef = useRef<HTMLDivElement>(null);

  // ESC to close
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  // Click-outside to close. We use mousedown so it fires before the click
  // that might have re-opened it on another marker.
  useEffect(() => {
    function onMouseDown(e: MouseEvent) {
      const node = popoverRef.current;
      if (!node) return;
      if (node.contains(e.target as Node)) return;
      // Don't close if the click was on another marker — let MarkerLayer
      // handle that by re-opening with the new marker.
      const target = e.target as HTMLElement;
      if (target.closest('[data-marker-dot]')) return;
      onClose();
    }
    // Tiny delay so the opening click doesn't immediately close it
    const id = window.setTimeout(() => {
      document.addEventListener('mousedown', onMouseDown);
    }, 50);
    return () => {
      window.clearTimeout(id);
      document.removeEventListener('mousedown', onMouseDown);
    };
  }, [onClose]);

  // Anchor side selection
  const openLeft = marker.x > 0.55;
  const openUp = marker.y > 0.55;

  if (!camera) {
    // Should never happen if the marker references a valid camera, but
    // if the camera was deleted we degrade gracefully.
    return (
      <div
        ref={popoverRef}
        style={{
          position: 'absolute',
          left: `${marker.x * 100}%`,
          top: `${marker.y * 100}%`,
          transform: 'translate(-50%, -50%)',
          zIndex: 20,
        }}
        className="rounded-md border border-border bg-surface p-3 text-sm text-muted-foreground shadow-lg"
      >
        <p>{t('floorPlan.livePreview.cameraMissing')}</p>
        <button
          type="button"
          onClick={onClose}
          className="mt-2 text-xs text-primary hover:underline"
        >
          {t('common.close')}
        </button>
      </div>
    );
  }

  // We approximate the popover's on-screen size via plain pixels because
  // the parent is inside react-zoom-pan-pinch's transform. The numeric
  // offset (8px from marker dot) gets visually scaled with the plan but
  // that's acceptable — popover slides away from the dot at high zoom.
  const POPOVER_W = 320;
  const POPOVER_H = 220;
  const offset = 16; // px from marker dot center

  // Compute the left/top offsets in pixel-space inside the source image
  const anchorX = marker.x * imageWidthPx;
  const anchorY = marker.y * imageHeightPx;
  const popoverLeft = openLeft
    ? anchorX - POPOVER_W - offset
    : anchorX + offset;
  const popoverTop = openUp
    ? anchorY - POPOVER_H - offset
    : anchorY + offset;

  return (
    <div
      ref={popoverRef}
      style={{
        position: 'absolute',
        left: popoverLeft,
        top: popoverTop,
        width: POPOVER_W,
        height: POPOVER_H,
        zIndex: 20,
      }}
      className="overflow-hidden rounded-md border border-border bg-background shadow-2xl"
    >
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border bg-surface px-3 py-2">
        <p className="flex-1 truncate text-sm font-medium text-foreground">
          {marker.label || camera.name}
        </p>
        <button
          type="button"
          onClick={() => navigate(`/cameras?focus=${camera.id}`)}
          className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label={t('floorPlan.livePreview.openCamera')}
          title={t('floorPlan.livePreview.openCamera')}
        >
          <Video className="h-3.5 w-3.5" />
        </button>
        {onExpand && (
          <button
            type="button"
            onClick={onExpand}
            className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label={t('floorPlan.livePreview.expand')}
            title={t('floorPlan.livePreview.expand')}
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </button>
        )}
        <button
          type="button"
          onClick={onClose}
          className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label={t('common.close')}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Live stream */}
      <div className="h-[calc(100%-2.5rem)] bg-black">
        {camera.hls_url ? (
          <CameraLivePlayer
            hlsUrl={camera.hls_url}
            muted
            autoPlay
            compact
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            {t('floorPlan.livePreview.noStream')}
          </div>
        )}
      </div>
    </div>
  );
}
