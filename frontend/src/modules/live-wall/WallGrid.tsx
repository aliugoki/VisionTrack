import { useState } from 'react';
import {
  DndContext,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { WallTile } from '@/modules/live-wall/WallTile';
import type { TileEntry } from '@/modules/live-wall/types';
import type { Camera } from '@/shared/types/api';

interface WallGridProps {
  rows: number;
  cols: number;
  tiles: TileEntry[];
  cameras: Camera[];
  editable: boolean;
  onTileChange: (index: number, cameraId: string | null) => void;
  /** Swap cameras between two tiles (e.g. from drag-and-drop). */
  onTileSwap: (fromIndex: number, toIndex: number) => void;
}

/**
 * The NxN grid.
 *
 * Layout:
 *   - Default: CSS grid with N rows × N cols, each tile 16:9 aspect
 *   - Fullscreen: one tile fills the entire grid area, others hidden
 *
 * Drag-and-drop is managed at this level via dnd-kit DndContext. We use
 * both pointer + touch sensors so it works on tablets in the warehouse.
 *
 * Performance note (4x4 = 16 streams):
 *   We rely on Batch B's IntersectionObserver in TrackOverlay to pause
 *   overlays on tiles scrolled offscreen. Video playback itself isn't
 *   paused — hls.js handles its own segment buffering and the GPU is
 *   doing the transcode regardless.
 */
export function WallGrid({
  rows,
  cols,
  tiles,
  cameras,
  editable,
  onTileChange,
  onTileSwap,
}: WallGridProps) {
  const [fullscreenIndex, setFullscreenIndex] = useState<number | null>(null);

  // Pointer sensor with a small activation distance prevents accidental
  // drags when the user is just clicking buttons inside a tile.
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 200, tolerance: 8 },
    })
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over) return;
    const from = (active.data.current as any)?.tileIndex;
    const to = (over.data.current as any)?.tileIndex;
    if (typeof from !== 'number' || typeof to !== 'number') return;
    if (from === to) return;
    onTileSwap(from, to);
  }

  // Clamp fullscreen index if the camera at that tile has been removed
  if (fullscreenIndex !== null && !tiles[fullscreenIndex]) {
    setFullscreenIndex(null);
  }

  function toggleFullscreen(index: number) {
    setFullscreenIndex((prev) => (prev === index ? null : index));
  }

  // Fullscreen mode: render only the focused tile, occupying the full grid area
  if (fullscreenIndex !== null) {
    return (
      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className="h-full">
          <WallTile
            key={fullscreenIndex}
            tileIndex={fullscreenIndex}
            cameraId={tiles[fullscreenIndex] ?? null}
            cameras={cameras}
            editable={editable}
            isFullscreen
            onAssign={(cid) => onTileChange(fullscreenIndex, cid)}
            onToggleFullscreen={() => toggleFullscreen(fullscreenIndex)}
          />
        </div>
      </DndContext>
    );
  }

  // Normal grid mode
  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <div
        className="grid gap-2"
        style={{
          gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
          gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))`,
        }}
      >
        {Array.from({ length: rows * cols }).map((_, i) => (
          <div key={i} className="aspect-video min-h-0">
            <WallTile
              tileIndex={i}
              cameraId={tiles[i] ?? null}
              cameras={cameras}
              editable={editable}
              isFullscreen={false}
              onAssign={(cid) => onTileChange(i, cid)}
              onToggleFullscreen={() => toggleFullscreen(i)}
            />
          </div>
        ))}
      </div>
    </DndContext>
  );
}
