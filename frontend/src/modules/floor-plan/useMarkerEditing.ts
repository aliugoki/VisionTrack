import { useCallback, useMemo, useState } from 'react';
import type { FloorPlanMarker } from '@/modules/floor-plan/types';

/**
 * Pure state hook for marker editing. Doesn't talk to the API — caller
 * loads initial markers and persists them via useUpdateFloorPlanMarkers.
 *
 * Editor modes:
 *   'idle'           — nothing selected, click on plan does nothing
 *   'placing'        — a camera is picked from the palette; next click on
 *                      the plan drops a new marker for that camera
 *   'selected'       — an existing marker is selected (click X removes,
 *                      drag repositions)
 *
 * The state is kept here rather than scattered in components so the
 * editor's behavior is one self-contained machine that's easy to test
 * mentally.
 */

type EditMode =
  | { kind: 'idle' }
  | { kind: 'placing'; cameraId: string }
  | { kind: 'selected'; markerId: string };

export interface UseMarkerEditingApi {
  markers: FloorPlanMarker[];
  mode: EditMode;
  dirty: boolean;
  /** True if a marker for this camera already exists. */
  isCameraPlaced: (cameraId: string) => boolean;
  /** Enter placing mode for the given camera. */
  pickForPlacement: (cameraId: string) => void;
  /** Drop the placement-mode camera at a fractional position. */
  placeAt: (x: number, y: number) => void;
  /** Select an existing marker. */
  selectMarker: (markerId: string) => void;
  /** Reposition an existing marker (drag). */
  moveMarker: (markerId: string, x: number, y: number) => void;
  /** Patch any subset of a marker's fields (used by cone editor). */
  patchMarker: (
    markerId: string,
    patch: Partial<FloorPlanMarker>
  ) => void;
  /** Remove the currently-selected marker. */
  removeSelected: () => void;
  /** Cancel any current mode and return to idle. */
  cancel: () => void;
  /** Reset to a fresh initial state (after save). */
  resetTo: (markers: FloorPlanMarker[]) => void;
}

// Lightweight UUID generator. crypto.randomUUID is widely supported.
function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  // Fallback for older environments — sufficient for client-side IDs.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v));
}

export function useMarkerEditing(
  initialMarkers: FloorPlanMarker[]
): UseMarkerEditingApi {
  const [markers, setMarkers] = useState<FloorPlanMarker[]>(initialMarkers);
  const [baseline, setBaseline] = useState<FloorPlanMarker[]>(initialMarkers);
  const [mode, setMode] = useState<EditMode>({ kind: 'idle' });

  const dirty = useMemo(() => {
    if (markers.length !== baseline.length) return true;
    // Compare by id + x + y + label + cone fields. Cheap because lists are small.
    const byId = new Map(baseline.map((m) => [m.id, m]));
    for (const m of markers) {
      const b = byId.get(m.id);
      if (!b) return true;
      if (b.camera_id !== m.camera_id) return true;
      if (Math.abs(b.x - m.x) > 1e-6) return true;
      if (Math.abs(b.y - m.y) > 1e-6) return true;
      if ((b.label || null) !== (m.label || null)) return true;
      if ((b.cone_angle_deg ?? null) !== (m.cone_angle_deg ?? null))
        return true;
      if ((b.cone_range ?? null) !== (m.cone_range ?? null)) return true;
      if (
        (b.cone_rotation_deg ?? null) !== (m.cone_rotation_deg ?? null)
      )
        return true;
    }
    return false;
  }, [markers, baseline]);

  const isCameraPlaced = useCallback(
    (cameraId: string) => markers.some((m) => m.camera_id === cameraId),
    [markers]
  );

  const pickForPlacement = useCallback((cameraId: string) => {
    setMode({ kind: 'placing', cameraId });
  }, []);

  const placeAt = useCallback((x: number, y: number) => {
    setMode((current) => {
      if (current.kind !== 'placing') return current;
      const newMarker: FloorPlanMarker = {
        id: newId(),
        camera_id: current.cameraId,
        x: clamp01(x),
        y: clamp01(y),
        label: null,
        // Cones default off; operator enables per marker in the sidebar.
        cone_angle_deg: null,
        cone_range: null,
        cone_rotation_deg: null,
      };
      setMarkers((prev) => [...prev, newMarker]);
      return { kind: 'selected', markerId: newMarker.id };
    });
  }, []);

  const selectMarker = useCallback((markerId: string) => {
    setMode({ kind: 'selected', markerId });
  }, []);

  const moveMarker = useCallback(
    (markerId: string, x: number, y: number) => {
      setMarkers((prev) =>
        prev.map((m) =>
          m.id === markerId ? { ...m, x: clamp01(x), y: clamp01(y) } : m
        )
      );
    },
    []
  );

  const patchMarker = useCallback(
    (markerId: string, patch: Partial<FloorPlanMarker>) => {
      setMarkers((prev) =>
        prev.map((m) => (m.id === markerId ? { ...m, ...patch } : m))
      );
    },
    []
  );

  const removeSelected = useCallback(() => {
    setMode((current) => {
      if (current.kind !== 'selected') return current;
      const target = current.markerId;
      setMarkers((prev) => prev.filter((m) => m.id !== target));
      return { kind: 'idle' };
    });
  }, []);

  const cancel = useCallback(() => setMode({ kind: 'idle' }), []);

  const resetTo = useCallback((next: FloorPlanMarker[]) => {
    setMarkers(next);
    setBaseline(next);
    setMode({ kind: 'idle' });
  }, []);

  return {
    markers,
    mode,
    dirty,
    isCameraPlaced,
    pickForPlacement,
    placeAt,
    selectMarker,
    moveMarker,
    patchMarker,
    removeSelected,
    cancel,
    resetTo,
  };
}
