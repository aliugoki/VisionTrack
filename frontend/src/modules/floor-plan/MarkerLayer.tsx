import { useCallback, useEffect, useRef, useState } from 'react';
import { Camera as CameraIcon, X } from 'lucide-react';
import { cn } from '@/shared/lib/cn';
import type { FloorPlanMarker } from '@/modules/floor-plan/types';
import type { Camera } from '@/shared/types/api';
import { CoverageCone } from '@/modules/floor-plan/CoverageCone';

interface MarkerLayerProps {
  markers: FloorPlanMarker[];
  cameras: Camera[];
  /** Currently-selected marker id (for highlight + delete affordance). */
  selectedMarkerId: string | null;
  /** Read-only viewer mode (Batch E live preview uses this). */
  editable: boolean;
  /** Current zoom scale from the TransformWrapper. Needed for drag math. */
  currentScale: number;
  /** Source image dimensions in pixels. */
  imageWidthPx: number;
  imageHeightPx: number;
  onSelectMarker: (markerId: string) => void;
  onMoveMarker: (markerId: string, x: number, y: number) => void;
  onRemoveSelected: () => void;
  /**
   * Optional: fired when a marker is clicked in non-editable (viewer) mode.
   * The parent uses this to open the live-preview popover (Batch E).
   * In editable mode, clicks always go to onSelectMarker instead.
   */
  onClickMarker?: (markerId: string) => void;
}

/**
 * Renders camera markers as absolutely-positioned children of the
 * floor-plan image. The parent is wrapped in TransformWrapper so the
 * markers automatically scale/pan with the image — we don't have to
 * recompute screen-space positions.
 *
 * Drag math:
 *   When the operator drags a marker, the pointermove deltas are in
 *   client (screen) pixels. To convert that into a fractional position
 *   delta we divide by:  scale * imageWidthPx
 *   The scale comes from TransformWrapper's render-prop context.
 *
 * Click vs drag:
 *   We treat any pointermove that exceeds a small threshold as a drag.
 *   Below the threshold, releasing counts as a click (selection).
 */
const DRAG_THRESHOLD_PX = 4;

export function MarkerLayer({
  markers,
  cameras,
  selectedMarkerId,
  editable,
  currentScale,
  imageWidthPx,
  imageHeightPx,
  onSelectMarker,
  onMoveMarker,
  onRemoveSelected,
  onClickMarker,
}: MarkerLayerProps) {
  return (
    <>
      {/* Coverage cones first, so marker dots paint on top of them */}
      {markers.map((m) => (
        <CoverageCone
          key={`cone-${m.id}`}
          marker={m}
          imageWidthPx={imageWidthPx}
          imageHeightPx={imageHeightPx}
          selected={m.id === selectedMarkerId}
        />
      ))}
      {markers.map((m) => (
        <Marker
          key={m.id}
          marker={m}
          camera={cameras.find((c) => c.id === m.camera_id)}
          selected={m.id === selectedMarkerId}
          editable={editable}
          currentScale={currentScale}
          imageWidthPx={imageWidthPx}
          imageHeightPx={imageHeightPx}
          // In editor mode, clicks select for editing. In viewer mode,
          // clicks fire onClickMarker (typically to open a live preview).
          onSelect={() => {
            if (editable) {
              onSelectMarker(m.id);
            } else if (onClickMarker) {
              onClickMarker(m.id);
            }
          }}
          onMove={(x, y) => onMoveMarker(m.id, x, y)}
          onRemove={onRemoveSelected}
        />
      ))}
    </>
  );
}

// -- individual marker --------------------------------------------------------
interface MarkerProps {
  marker: FloorPlanMarker;
  camera?: Camera;
  selected: boolean;
  editable: boolean;
  currentScale: number;
  imageWidthPx: number;
  imageHeightPx: number;
  onSelect: () => void;
  onMove: (x: number, y: number) => void;
  onRemove: () => void;
}

function Marker({
  marker,
  camera,
  selected,
  editable,
  currentScale,
  imageWidthPx,
  imageHeightPx,
  onSelect,
  onMove,
  onRemove,
}: MarkerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState(false);
  // Track drag start so we can distinguish click from drag
  const dragRef = useRef<{
    startX: number;
    startY: number;
    startMarkerX: number;
    startMarkerY: number;
    moved: boolean;
  } | null>(null);

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      // Prevent the pan handler in TransformWrapper from also reacting.
      // We do this in both editor and viewer mode — in viewer we still
      // want clicks to dispatch (for live-preview popup), and we still
      // need to stop the pan handler from interpreting it as a drag.
      e.stopPropagation();
      e.preventDefault();
      try {
        (e.target as Element).setPointerCapture(e.pointerId);
      } catch {
        // ignore — capture may not be supported on the element
      }
      dragRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        startMarkerX: marker.x,
        startMarkerY: marker.y,
        moved: false,
      };
    },
    [marker.x, marker.y]
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      // Only editable markers can be dragged. In viewer mode we track
      // pointerdown→up just to detect a click; no movement updates.
      if (!editable || !dragRef.current) return;
      const dx = e.clientX - dragRef.current.startX;
      const dy = e.clientY - dragRef.current.startY;
      const distance = Math.hypot(dx, dy);
      if (!dragRef.current.moved && distance < DRAG_THRESHOLD_PX) return;
      dragRef.current.moved = true;
      // Convert client-pixel delta to fractional delta accounting for zoom.
      const dxFrac = dx / (imageWidthPx * currentScale);
      const dyFrac = dy / (imageHeightPx * currentScale);
      onMove(
        dragRef.current.startMarkerX + dxFrac,
        dragRef.current.startMarkerY + dyFrac
      );
    },
    [editable, imageWidthPx, imageHeightPx, currentScale, onMove]
  );

  const onPointerUp = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!dragRef.current) return;
      const wasClick = !dragRef.current.moved;
      dragRef.current = null;
      try {
        (e.target as Element).releasePointerCapture(e.pointerId);
      } catch {
        // ignore
      }
      if (wasClick) onSelect();
    },
    [onSelect]
  );

  // Markers absolute-positioned inside the source-coordinate container.
  // Translate(-50%, -50%) so x/y point to the marker's center, not corner.
  return (
    <div
      ref={ref}
      data-marker-dot
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: 'absolute',
        left: `${marker.x * 100}%`,
        top: `${marker.y * 100}%`,
        // Counter the zoom scale on the marker itself so it stays a
        // constant visual size as the image zooms. Without this, dots
        // become huge at 4x zoom and unreadable at 0.3x.
        transform: `translate(-50%, -50%) scale(${1 / currentScale})`,
        transformOrigin: 'center',
        cursor: editable ? 'grab' : 'pointer',
        touchAction: 'none',
      }}
      className="z-10"
    >
      <div
        className={cn(
          'relative flex h-7 w-7 items-center justify-center rounded-full border-2 shadow-md transition-colors',
          selected
            ? 'border-primary bg-primary text-primary-foreground'
            : 'border-white bg-foreground text-background hover:bg-primary hover:border-primary hover:text-primary-foreground'
        )}
      >
        <CameraIcon className="h-3.5 w-3.5" />

        {/* Remove button — only when this marker is selected and editable */}
        {selected && editable && (
          <button
            type="button"
            onPointerDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              onRemove();
            }}
            className="absolute -end-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full bg-danger text-danger-foreground shadow hover:scale-110"
            aria-label="Remove marker"
          >
            <X className="h-2.5 w-2.5" />
          </button>
        )}
      </div>

      {/* Label tooltip on hover or when selected */}
      {(hovered || selected) && (
        <div
          className="pointer-events-none absolute start-1/2 top-full mt-1 -translate-x-1/2 whitespace-nowrap rounded bg-foreground px-1.5 py-0.5 text-xs text-background shadow"
        >
          {marker.label || camera?.name || 'Unknown camera'}
        </div>
      )}
    </div>
  );
}
