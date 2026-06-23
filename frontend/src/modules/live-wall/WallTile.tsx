import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useDraggable, useDroppable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import {
  Plus,
  X,
  Video,
  Maximize2,
  Minimize2,
  GripVertical,
  MapPin,
} from 'lucide-react';
import { cn } from '@/shared/lib/cn';
import { Badge } from '@/shared/components/Badge';
import { CameraLivePlayer } from '@/modules/cameras/CameraLivePlayer';
import type { Camera } from '@/shared/types/api';

interface WallTileProps {
  /** Index of this tile in the grid. Used as the dnd-kit id. */
  tileIndex: number;
  /** UUID of the assigned camera, or null if empty. */
  cameraId: string | null;
  /** Full list of cameras in the tenant — used for the picker dropdown. */
  cameras: Camera[];
  /** Called when the user picks (or clears) a camera for this tile. */
  onAssign: (cameraId: string | null) => void;
  /** When false, picker dropdowns and drag handles are hidden (view mode). */
  editable: boolean;
  /** True when this tile is the currently-fullscreen tile. */
  isFullscreen: boolean;
  /** Toggle fullscreen for this tile. */
  onToggleFullscreen: () => void;
}

/**
 * One cell of the Live Wall.
 *
 * Drag-and-drop:
 *   In edit mode, each tile is both a draggable and a droppable. Dragging
 *   one tile onto another swaps their camera assignments. Tiles without
 *   a camera assigned are still droppable (you can move a camera into
 *   an empty slot) but not draggable.
 *
 * Fullscreen:
 *   Double-clicking a populated tile expands it to fill the grid via
 *   parent state. Click the minimize button to return to grid view.
 */
export function WallTile({
  tileIndex,
  cameraId,
  cameras,
  onAssign,
  editable,
  isFullscreen,
  onToggleFullscreen,
}: WallTileProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [pickerOpen, setPickerOpen] = useState(false);

  const camera = useMemo(
    () => (cameraId ? cameras.find((c) => c.id === cameraId) : undefined),
    [cameraId, cameras]
  );

  // dnd-kit hooks. Draggable only when editable AND a camera is assigned —
  // empty tiles don't need a drag handle. Droppable always (so an empty
  // tile can accept a drop).
  const isDraggable = editable && !!camera;

  const {
    attributes,
    listeners,
    setNodeRef: setDragRef,
    transform,
    isDragging,
  } = useDraggable({
    id: `tile-${tileIndex}`,
    data: { tileIndex, cameraId },
    disabled: !isDraggable,
  });

  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `drop-${tileIndex}`,
    data: { tileIndex },
    disabled: !editable,
  });

  // Combine the drag and drop refs on the wrapper element
  const setRefs = (el: HTMLElement | null) => {
    setDragRef(el);
    setDropRef(el);
  };

  const style = {
    transform: CSS.Translate.toString(transform),
    opacity: isDragging ? 0.4 : 1,
  };

  // If camera was assigned but later deleted, treat as broken state.
  if (cameraId && !camera) {
    return (
      <div
        ref={setRefs}
        style={style}
        className={cn(
          'relative flex h-full items-center justify-center rounded-md border border-dashed border-danger/40 bg-danger/5 p-2',
          isOver && 'ring-2 ring-primary ring-offset-1 ring-offset-background'
        )}
      >
        <span className="text-xs text-danger">
          {t('liveWall.tile.missingCamera')}
        </span>
        {editable && (
          <button
            type="button"
            onClick={() => onAssign(null)}
            className="absolute end-2 top-2 rounded-full bg-background/80 p-1 text-danger hover:bg-danger hover:text-danger-foreground"
            aria-label={t('common.delete')}
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>
    );
  }

  if (!camera) {
    // Empty tile — droppable but not draggable
    return (
      <div
        ref={setRefs}
        style={style}
        className={cn(
          'relative h-full',
          isOver && 'ring-2 ring-primary ring-offset-1 ring-offset-background rounded-md'
        )}
      >
        <button
          type="button"
          onClick={() => editable && setPickerOpen((v) => !v)}
          disabled={!editable}
          className={cn(
            'group flex h-full w-full flex-col items-center justify-center gap-2 rounded-md border-2 border-dashed transition-colors',
            editable
              ? 'border-border bg-muted/20 hover:border-primary hover:bg-primary/5 cursor-pointer'
              : 'border-border/40 bg-muted/10 cursor-default'
          )}
        >
          {editable ? (
            <>
              <Plus className="h-6 w-6 text-muted-foreground group-hover:text-primary" />
              <span className="text-xs text-muted-foreground group-hover:text-primary">
                {t('liveWall.tile.addCamera')}
              </span>
            </>
          ) : (
            <>
              <Video className="h-6 w-6 text-muted-foreground/40" />
              <span className="text-xs text-muted-foreground/60">
                {t('liveWall.tile.empty')}
              </span>
            </>
          )}
        </button>

        {pickerOpen && editable && (
          <CameraPicker
            cameras={cameras}
            onPick={(id) => {
              onAssign(id);
              setPickerOpen(false);
            }}
            onClose={() => setPickerOpen(false)}
          />
        )}
      </div>
    );
  }

  // Camera assigned — full tile with live player
  return (
    <div
      ref={setRefs}
      style={style}
      onDoubleClick={onToggleFullscreen}
      className={cn(
        'relative h-full overflow-hidden rounded-md bg-black',
        isOver && 'ring-2 ring-primary ring-offset-1 ring-offset-background',
        isDragging && 'cursor-grabbing'
      )}
    >
      <CameraLivePlayer
        hlsUrl={camera.hls_url}
        label={camera.mediamtx_path}
        cameraId={camera.id}
        compact
        autoPlay
        // Tiles are small — labels and trails are visual clutter at 480x270.
        // The full-preview dialog defaults them on; tiles default them off.
        overlayDefaults={{ enabled: true, showLabels: false, showTrails: false }}
        hideOverlayControls
        className="h-full w-full"
      />
      {/* Top bar — camera name + status */}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex items-start justify-between gap-2 p-2">
        <div className="rounded bg-background/70 px-2 py-0.5 text-xs font-medium text-foreground backdrop-blur-sm">
          {camera.name}
        </div>
        <Badge
          tone={camera.status === 'online' ? 'success' : 'danger'}
          dot
          pulse={camera.status === 'online'}
        >
          {t(`cameras.status.${camera.status}`)}
        </Badge>
      </div>

      {/* Tile actions — top-right cluster of icon buttons */}
      <div className="absolute end-2 top-9 z-10 flex flex-col gap-1">
        {/* Drag handle — only in edit mode */}
        {editable && (
          <button
            type="button"
            {...listeners}
            {...attributes}
            className="rounded-full bg-background/70 p-1.5 text-foreground backdrop-blur-sm hover:bg-primary hover:text-primary-foreground cursor-grab active:cursor-grabbing"
            aria-label={t('liveWall.tile.dragHint')}
            title={t('liveWall.tile.dragHint')}
          >
            <GripVertical className="h-3.5 w-3.5" />
          </button>
        )}
        {/* Floor-plan jump — visible when camera is placed on at least one plan.
            If there's only one plan, jump directly. If multiple, jump to the
            first one (we could add a picker later if this is common; for now
            keeping the tile UI uncluttered). */}
        {camera.floor_plan_locations?.length > 0 && (
          <button
            type="button"
            onClick={() => {
              const loc = camera.floor_plan_locations[0];
              navigate(
                `/floor-plan?preview=${loc.plan_id}&openMarker=${loc.marker_id}`
              );
            }}
            className="rounded-full bg-background/70 p-1.5 text-foreground backdrop-blur-sm hover:bg-foreground hover:text-background"
            aria-label={t('liveWall.tile.showOnFloorPlan')}
            title={t('liveWall.tile.showOnFloorPlan')}
          >
            <MapPin className="h-3.5 w-3.5" />
          </button>
        )}
        {/* Fullscreen toggle — always available when camera assigned */}
        <button
          type="button"
          onClick={onToggleFullscreen}
          className="rounded-full bg-background/70 p-1.5 text-foreground backdrop-blur-sm hover:bg-foreground hover:text-background"
          aria-label={
            isFullscreen
              ? t('liveWall.tile.exitFullscreen')
              : t('liveWall.tile.fullscreen')
          }
          title={
            isFullscreen
              ? t('liveWall.tile.exitFullscreen')
              : t('liveWall.tile.fullscreen')
          }
        >
          {isFullscreen ? (
            <Minimize2 className="h-3.5 w-3.5" />
          ) : (
            <Maximize2 className="h-3.5 w-3.5" />
          )}
        </button>
      </div>

      {/* Remove button — bottom-right, edit mode only */}
      {editable && (
        <button
          type="button"
          onClick={() => onAssign(null)}
          className="absolute end-2 bottom-2 z-10 rounded-full bg-background/70 p-1.5 text-foreground backdrop-blur-sm hover:bg-danger hover:text-danger-foreground"
          aria-label={t('liveWall.tile.clear')}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

// -- Camera picker dropdown ---------------------------------------------------
function CameraPicker({
  cameras,
  onPick,
  onClose,
}: {
  cameras: Camera[];
  onPick: (id: string) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return cameras;
    return cameras.filter((c) => c.name.toLowerCase().includes(q));
  }, [cameras, search]);

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-10 cursor-default"
        onClick={onClose}
        aria-label="Close picker"
      />
      <div className="absolute inset-x-2 top-2 z-20 max-h-64 overflow-hidden rounded-md border border-border bg-surface shadow-xl">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          autoFocus
          placeholder={t('liveWall.tile.searchCamera')}
          className="w-full border-b border-border bg-transparent px-3 py-2 text-sm focus:outline-none"
        />
        <ul className="max-h-48 overflow-y-auto">
          {filtered.length === 0 ? (
            <li className="px-3 py-2 text-xs text-muted-foreground">
              {t('liveWall.tile.noCameras')}
            </li>
          ) : (
            filtered.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => onPick(c.id)}
                  className="flex w-full items-center justify-between gap-2 px-3 py-2 text-start text-sm hover:bg-muted"
                >
                  <span className="truncate">{c.name}</span>
                  <span
                    className={cn(
                      'h-1.5 w-1.5 rounded-full',
                      c.status === 'online'
                        ? 'bg-success'
                        : 'bg-muted-foreground'
                    )}
                  />
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
    </>
  );
}
