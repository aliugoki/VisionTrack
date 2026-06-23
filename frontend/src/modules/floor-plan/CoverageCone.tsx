import type { FloorPlanMarker } from '@/modules/floor-plan/types';

interface CoverageConeProps {
  marker: FloorPlanMarker;
  /** Source image dimensions in pixels — needed for cone scaling. */
  imageWidthPx: number;
  imageHeightPx: number;
  /** Highlight color when the marker is selected. */
  selected: boolean;
}

/**
 * Renders a marker's coverage cone as a pie-slice SVG positioned over
 * the floor plan image.
 *
 * Geometry:
 *   - Origin (the marker's position) is the apex of the pie slice
 *   - Range is fractional relative to the image's WIDTH (we use width
 *     for both x and y range so the cone shape doesn't distort on
 *     non-square plans)
 *   - Rotation is degrees clockwise from "east" (positive x-axis), so
 *     0° = camera looks right, 90° = down, 180° = left, 270° = up.
 *   - Angle is the total FOV sweep. The cone is symmetric around the
 *     rotation direction: a 90° cone rotated 0° spans -45°..+45° from east.
 *
 * Visual style:
 *   - Pale fill so it's visible without obscuring the plan
 *   - Strong stroke on the boundary edges for clarity at small zoom
 *   - Color shifts to primary when the marker is selected (editor only)
 *
 * SVG coordinate system: we render in source-pixel space (matches the
 * parent <div style={{width: imageWidthPx, height: imageHeightPx}}>),
 * so the SVG inherits the floor plan's zoom/pan transform from
 * react-zoom-pan-pinch automatically. No manual scale math needed.
 */
export function CoverageCone({
  marker,
  imageWidthPx,
  imageHeightPx,
  selected,
}: CoverageConeProps) {
  // If any cone field is missing, render nothing
  if (
    marker.cone_angle_deg == null ||
    marker.cone_range == null ||
    marker.cone_rotation_deg == null
  ) {
    return null;
  }

  const cx = marker.x * imageWidthPx;
  const cy = marker.y * imageHeightPx;
  const r = marker.cone_range * imageWidthPx;
  const halfAngleRad = (marker.cone_angle_deg / 2) * (Math.PI / 180);
  const rotationRad = marker.cone_rotation_deg * (Math.PI / 180);

  // Two boundary points of the pie slice
  const x1 = cx + r * Math.cos(rotationRad - halfAngleRad);
  const y1 = cy + r * Math.sin(rotationRad - halfAngleRad);
  const x2 = cx + r * Math.cos(rotationRad + halfAngleRad);
  const y2 = cy + r * Math.sin(rotationRad + halfAngleRad);

  // SVG arc: large-arc-flag = 1 if the angle > 180°, else 0
  const largeArc = marker.cone_angle_deg > 180 ? 1 : 0;

  // Pie slice path: move to center, line to first edge, arc to second edge, close
  const path =
    `M ${cx} ${cy} ` +
    `L ${x1} ${y1} ` +
    `A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} ` +
    `Z`;

  // Color scheme — selected uses theme primary, otherwise a calm neutral
  const fillColor = selected
    ? 'rgba(59, 130, 246, 0.20)' // tailwind primary-ish at 20%
    : 'rgba(100, 116, 139, 0.18)'; // slate at 18%
  const strokeColor = selected
    ? 'rgba(59, 130, 246, 0.85)'
    : 'rgba(100, 116, 139, 0.55)';

  return (
    <svg
      // SVG fills its parent positioning context; we use pointer-events:none
      // so clicks pass through to either the click overlay or the marker dot
      // depending on where the user clicked.
      style={{
        position: 'absolute',
        left: 0,
        top: 0,
        width: imageWidthPx,
        height: imageHeightPx,
        pointerEvents: 'none',
        // Below the marker dots (z-10) so the dots stay clickable
        zIndex: 5,
      }}
      viewBox={`0 0 ${imageWidthPx} ${imageHeightPx}`}
      preserveAspectRatio="none"
    >
      <path
        d={path}
        fill={fillColor}
        stroke={strokeColor}
        strokeWidth={selected ? 2 : 1.5}
        // Don't scale the stroke with the transform — it'd vanish at small
        // zoom and balloon at large zoom. vector-effect keeps it constant.
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
