import { useCallback, useEffect, useRef } from 'react';
import type { Zone, ZonePoint } from '@/modules/floor-plan/types';

interface ZonePolygonLayerProps {
  zones: Zone[];
  /** Currently-selected zone id (highlighted, vertices draggable). */
  selectedZoneId: string | null;
  /** When in draw mode, the in-progress draft polygon to render. */
  draftPoints: ZonePoint[] | null;
  /** Draft color while drawing — matches what the operator picked. */
  draftColor: string | null;
  /** Read-only mode: render polygons + fills, no vertex handles. */
  editable: boolean;
  /** Current zoom scale from the TransformWrapper — used to keep vertex
   *  handles a constant on-screen size. */
  currentScale: number;
  imageWidthPx: number;
  imageHeightPx: number;
  onSelectZone: (zoneId: string) => void;
  onMoveVertex: (zoneId: string, vertexIndex: number, x: number, y: number) => void;
  onDeleteVertex: (zoneId: string, vertexIndex: number) => void;
}

/**
 * Renders all zone polygons over the floor plan.
 *
 * Layering:
 *   - One SVG element covers the whole source-pixel container (filled
 *     polygons + outlines + edge lines for the draft)
 *   - Vertex handles are HTML divs (not SVG) so they can use the same
 *     counter-scale-on-zoom trick the marker dots use, keeping them
 *     a constant size at any zoom level.
 *
 * Pointer events:
 *   - The polygon `<path>` elements are clickable in editable mode
 *     (to select a zone). In viewer mode the SVG has pointer-events:none.
 *   - Vertex handles capture pointer events explicitly and stop propagation
 *     so the TransformWrapper's pan handler doesn't reset their drag.
 *   - A live preview of the next edge during drawing is rendered as a
 *     dashed line from the last draft vertex to the cursor; we let
 *     FloorPlanEditPage manage the cursor position via the parent's
 *     onPlaneMouseMove (handled at the page level so it can update).
 */
export function ZonePolygonLayer({
  zones,
  selectedZoneId,
  draftPoints,
  draftColor,
  editable,
  currentScale,
  imageWidthPx,
  imageHeightPx,
  onSelectZone,
  onMoveVertex,
  onDeleteVertex,
}: ZonePolygonLayerProps) {
  // We render zone polygons in two passes: filled bodies first (lower
  // z-index inside the SVG, which by SVG paint order means earlier in DOM),
  // then the selected zone's outline on top with a heavier stroke so it
  // visually dominates when fine-tuning.
  const drawing = draftPoints !== null;

  return (
    <>
      {/* Main SVG: zone fills + outlines + draft. Spans the full source-px area. */}
      <svg
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: imageWidthPx,
          height: imageHeightPx,
          // In editor mode SVG receives clicks (so polygon selection works).
          // In viewer it's purely decorative.
          pointerEvents: editable ? 'auto' : 'none',
          zIndex: 4,
        }}
        viewBox={`0 0 ${imageWidthPx} ${imageHeightPx}`}
        preserveAspectRatio="none"
      >
        {/* Existing zones */}
        {zones.map((z) => {
          const selected = z.id === selectedZoneId;
          const pts = z.polygon
            .map((p) => `${p.x * imageWidthPx},${p.y * imageHeightPx}`)
            .join(' ');
          return (
            <polygon
              key={z.id}
              points={pts}
              fill={z.color + (selected ? '40' : '26')}
              stroke={z.color}
              strokeWidth={selected ? 2.5 : 1.5}
              vectorEffect="non-scaling-stroke"
              style={{
                cursor: editable && !drawing ? 'pointer' : 'default',
                pointerEvents: editable && !drawing ? 'auto' : 'none',
              }}
              onClick={(e) => {
                if (!editable || drawing) return;
                e.stopPropagation();
                onSelectZone(z.id);
              }}
            />
          );
        })}

        {/* Draft polygon — in-progress drawing */}
        {draftPoints && draftColor && draftPoints.length > 0 && (
          <>
            {/* Closed-loop preview (only when ≥3 points; preview the polygon as it'd close) */}
            {draftPoints.length >= 3 && (
              <polygon
                points={draftPoints
                  .map((p) => `${p.x * imageWidthPx},${p.y * imageHeightPx}`)
                  .join(' ')}
                fill={draftColor + '22'}
                stroke={draftColor}
                strokeWidth={2}
                strokeDasharray="6 4"
                vectorEffect="non-scaling-stroke"
                pointerEvents="none"
              />
            )}
            {/* Open polyline — connects all draft points so far */}
            {draftPoints.length < 3 && draftPoints.length >= 2 && (
              <polyline
                points={draftPoints
                  .map((p) => `${p.x * imageWidthPx},${p.y * imageHeightPx}`)
                  .join(' ')}
                fill="none"
                stroke={draftColor}
                strokeWidth={2}
                strokeDasharray="6 4"
                vectorEffect="non-scaling-stroke"
                pointerEvents="none"
              />
            )}
          </>
        )}
      </svg>

      {/* Vertex handles — HTML divs over the SVG.
          Rendered only for the selected zone or the draft polygon, so we
          don't pile dozens of dots over the floor plan in idle mode. */}
      {editable && selectedZoneId && (
        <VertexHandles
          zone={zones.find((z) => z.id === selectedZoneId)}
          imageWidthPx={imageWidthPx}
          imageHeightPx={imageHeightPx}
          currentScale={currentScale}
          onMove={onMoveVertex}
          onDelete={onDeleteVertex}
        />
      )}
      {editable && draftPoints && draftColor && draftPoints.length > 0 && (
        <DraftVertexDots
          points={draftPoints}
          color={draftColor}
          imageWidthPx={imageWidthPx}
          imageHeightPx={imageHeightPx}
          currentScale={currentScale}
        />
      )}
    </>
  );
}

// -- Vertex handles for the selected zone ------------------------------------

interface VertexHandlesProps {
  zone: Zone | undefined;
  imageWidthPx: number;
  imageHeightPx: number;
  currentScale: number;
  onMove: (zoneId: string, vertexIndex: number, x: number, y: number) => void;
  onDelete: (zoneId: string, vertexIndex: number) => void;
}

function VertexHandles({
  zone,
  imageWidthPx,
  imageHeightPx,
  currentScale,
  onMove,
  onDelete,
}: VertexHandlesProps) {
  if (!zone) return null;

  return (
    <>
      {zone.polygon.map((point, idx) => (
        <Vertex
          key={`${zone.id}-${idx}`}
          zoneId={zone.id}
          vertexIndex={idx}
          point={point}
          color={zone.color}
          imageWidthPx={imageWidthPx}
          imageHeightPx={imageHeightPx}
          currentScale={currentScale}
          canDelete={zone.polygon.length > 3}
          onMove={onMove}
          onDelete={onDelete}
        />
      ))}
    </>
  );
}

interface VertexProps {
  zoneId: string;
  vertexIndex: number;
  point: ZonePoint;
  color: string;
  imageWidthPx: number;
  imageHeightPx: number;
  currentScale: number;
  canDelete: boolean;
  onMove: (zoneId: string, vertexIndex: number, x: number, y: number) => void;
  onDelete: (zoneId: string, vertexIndex: number) => void;
}

function Vertex({
  zoneId,
  vertexIndex,
  point,
  color,
  imageWidthPx,
  imageHeightPx,
  currentScale,
  canDelete,
  onMove,
  onDelete,
}: VertexProps) {
  const dragRef = useRef<{ startX: number; startY: number } | null>(null);

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      // Right-click → delete (if allowed)
      if (e.button === 2) {
        e.preventDefault();
        e.stopPropagation();
        if (canDelete) onDelete(zoneId, vertexIndex);
        return;
      }
      // Left-click → start drag
      e.stopPropagation();
      e.preventDefault();
      try {
        (e.target as Element).setPointerCapture(e.pointerId);
      } catch {
        // ignore
      }
      dragRef.current = { startX: e.clientX, startY: e.clientY };
    },
    [zoneId, vertexIndex, canDelete, onDelete]
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (!dragRef.current) return;
      const dx = e.clientX - dragRef.current.startX;
      const dy = e.clientY - dragRef.current.startY;
      // Convert client-pixel delta to fractional delta, accounting for zoom
      const dxFrac = dx / (imageWidthPx * currentScale);
      const dyFrac = dy / (imageHeightPx * currentScale);
      // Update against the original point (use the current point as base
      // and replace it; the consumer hook clamps to 0..1)
      onMove(zoneId, vertexIndex, point.x + dxFrac, point.y + dyFrac);
      dragRef.current = { startX: e.clientX, startY: e.clientY };
    },
    [imageWidthPx, imageHeightPx, currentScale, onMove, zoneId, vertexIndex, point.x, point.y]
  );

  const onPointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = null;
    try {
      (e.target as Element).releasePointerCapture(e.pointerId);
    } catch {
      // ignore
    }
  }, []);

  return (
    <div
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onContextMenu={(e) => e.preventDefault()}
      style={{
        position: 'absolute',
        left: `${point.x * 100}%`,
        top: `${point.y * 100}%`,
        transform: `translate(-50%, -50%) scale(${1 / currentScale})`,
        transformOrigin: 'center',
        width: 14,
        height: 14,
        borderRadius: '50%',
        background: '#fff',
        border: `2.5px solid ${color}`,
        boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
        cursor: 'grab',
        zIndex: 11,
        touchAction: 'none',
      }}
      title={canDelete ? 'Drag to move • Right-click to delete' : 'Drag to move'}
    />
  );
}

// -- Draft vertex dots (during drawing) --------------------------------------

interface DraftVertexDotsProps {
  points: ZonePoint[];
  color: string;
  imageWidthPx: number;
  imageHeightPx: number;
  currentScale: number;
}

function DraftVertexDots({
  points,
  color,
  imageWidthPx,
  imageHeightPx,
  currentScale,
}: DraftVertexDotsProps) {
  return (
    <>
      {points.map((p, i) => {
        const isFirst = i === 0;
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: `${p.x * 100}%`,
              top: `${p.y * 100}%`,
              transform: `translate(-50%, -50%) scale(${1 / currentScale})`,
              transformOrigin: 'center',
              width: isFirst ? 16 : 12,
              height: isFirst ? 16 : 12,
              borderRadius: '50%',
              background: isFirst ? color : '#fff',
              border: `2px solid ${color}`,
              boxShadow: '0 1px 2px rgba(0,0,0,0.25)',
              pointerEvents: 'none',
              zIndex: 11,
            }}
          />
        );
      })}
    </>
  );
}
