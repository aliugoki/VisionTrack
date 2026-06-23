import { useCallback, useMemo, useState } from 'react';
import {
  DEFAULT_ZONE_COLOR,
  newId,
  type Zone,
  type ZonePoint,
  type ZoneRule,
} from '@/modules/floor-plan/types';

// State machine:
//   idle      — nothing in progress; can click a zone to select it
//   drawing   — operator clicked "New zone"; each plan-click adds a vertex,
//               double-click or first-vertex click closes the polygon
//   selected  — a zone is selected; name/color editable; vertices draggable
type EditMode =
  | { kind: 'idle' }
  | { kind: 'drawing'; draftPoints: ZonePoint[]; color: string }
  | { kind: 'selected'; zoneId: string };

const MIN_VERTICES = 3;
const MAX_VERTICES = 64;

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v));
}

export interface UseZoneEditingApi {
  zones: Zone[];
  mode: EditMode;
  dirty: boolean;

  // Drawing lifecycle
  startDrawing: (color?: string) => void;
  addDraftVertex: (x: number, y: number) => void;
  finishDrawing: (defaultName: string) => string | null;
  cancelDrawing: () => void;

  // Selection
  selectZone: (zoneId: string) => void;
  clearSelection: () => void;

  // Editing
  patchSelected: (patch: Partial<Pick<Zone, 'name' | 'color'>>) => void;
  moveVertex: (zoneId: string, vertexIndex: number, x: number, y: number) => void;
  deleteVertex: (zoneId: string, vertexIndex: number) => void;
  removeSelected: () => void;

  // Rules (Batch D)
  addRule: (zoneId: string, rule: ZoneRule) => void;
  updateRule: (zoneId: string, ruleId: string, next: ZoneRule) => void;
  deleteRule: (zoneId: string, ruleId: string) => void;

  // Persistence helpers
  resetTo: (zones: Zone[]) => void;
}

/**
 * Hook that owns zone-editing state for FloorPlanEditPage.
 *
 * State transitions:
 *
 *   idle → drawing       (startDrawing)
 *   drawing → idle       (cancelDrawing — ESC or Cancel button)
 *   drawing → selected   (finishDrawing — vertex >= 3, polygon closed)
 *   idle ↔ selected      (selectZone / clearSelection)
 *   selected → idle      (removeSelected)
 *
 * dirty flag fires when the current zones differ from the baseline
 * (the last server-saved or freshly-reset state). The editor uses
 * this to enable/disable the Save button and warn on discard.
 */
export function useZoneEditing(initial: Zone[]): UseZoneEditingApi {
  const [zones, setZones] = useState<Zone[]>(initial);
  const [baseline, setBaseline] = useState<Zone[]>(initial);
  const [mode, setMode] = useState<EditMode>({ kind: 'idle' });

  // --- Drawing ---------------------------------------------------------------

  const startDrawing = useCallback((color?: string) => {
    setMode({
      kind: 'drawing',
      draftPoints: [],
      color: color || DEFAULT_ZONE_COLOR,
    });
  }, []);

  const addDraftVertex = useCallback((x: number, y: number) => {
    setMode((current) => {
      if (current.kind !== 'drawing') return current;
      if (current.draftPoints.length >= MAX_VERTICES) return current;
      return {
        ...current,
        draftPoints: [
          ...current.draftPoints,
          { x: clamp01(x), y: clamp01(y) },
        ],
      };
    });
  }, []);

  const finishDrawing = useCallback(
    (defaultName: string) => {
      let createdId: string | null = null;
      setMode((current) => {
        if (current.kind !== 'drawing') return current;
        if (current.draftPoints.length < MIN_VERTICES) {
          // Don't close — operator needs more vertices
          return current;
        }
        const newZone: Zone = {
          id: newId(),
          name: defaultName,
          color: current.color,
          polygon: current.draftPoints,
          rules: [],
        };
        createdId = newZone.id;
        setZones((prev) => [...prev, newZone]);
        return { kind: 'selected', zoneId: newZone.id };
      });
      return createdId;
    },
    []
  );

  const cancelDrawing = useCallback(() => {
    setMode((current) => (current.kind === 'drawing' ? { kind: 'idle' } : current));
  }, []);

  // --- Selection -------------------------------------------------------------

  const selectZone = useCallback((zoneId: string) => {
    setMode({ kind: 'selected', zoneId });
  }, []);

  const clearSelection = useCallback(() => {
    setMode((current) =>
      current.kind === 'selected' ? { kind: 'idle' } : current
    );
  }, []);

  // --- Editing ---------------------------------------------------------------

  const patchSelected = useCallback(
    (patch: Partial<Pick<Zone, 'name' | 'color'>>) => {
      setMode((m) => {
        if (m.kind !== 'selected') return m;
        setZones((prev) =>
          prev.map((z) => (z.id === m.zoneId ? { ...z, ...patch } : z))
        );
        return m;
      });
    },
    []
  );

  const moveVertex = useCallback(
    (zoneId: string, vertexIndex: number, x: number, y: number) => {
      setZones((prev) =>
        prev.map((z) => {
          if (z.id !== zoneId) return z;
          if (vertexIndex < 0 || vertexIndex >= z.polygon.length) return z;
          const next = z.polygon.slice();
          next[vertexIndex] = { x: clamp01(x), y: clamp01(y) };
          return { ...z, polygon: next };
        })
      );
    },
    []
  );

  const deleteVertex = useCallback(
    (zoneId: string, vertexIndex: number) => {
      setZones((prev) =>
        prev.map((z) => {
          if (z.id !== zoneId) return z;
          // Must keep at least 3 vertices to remain a polygon
          if (z.polygon.length <= MIN_VERTICES) return z;
          if (vertexIndex < 0 || vertexIndex >= z.polygon.length) return z;
          const next = z.polygon.slice();
          next.splice(vertexIndex, 1);
          return { ...z, polygon: next };
        })
      );
    },
    []
  );

  const removeSelected = useCallback(() => {
    setMode((m) => {
      if (m.kind !== 'selected') return m;
      setZones((prev) => prev.filter((z) => z.id !== m.zoneId));
      return { kind: 'idle' };
    });
  }, []);

  // --- Rules (Batch D) -------------------------------------------------------

  /**
   * Append a new rule to a zone. The caller (rule edit modal) constructs
   * the rule via `newRule(kind)` and the optional form edits, then calls
   * this on Apply. No id mutation here — `newRule()` already generated one.
   */
  const addRule = useCallback((zoneId: string, rule: ZoneRule) => {
    setZones((prev) =>
      prev.map((z) =>
        z.id === zoneId ? { ...z, rules: [...z.rules, rule] } : z
      )
    );
  }, []);

  /**
   * Replace a rule by id with the next version. The modal works on a
   * full-rule copy and writes back the whole thing — simpler than diffing.
   */
  const updateRule = useCallback(
    (zoneId: string, ruleId: string, next: ZoneRule) => {
      setZones((prev) =>
        prev.map((z) => {
          if (z.id !== zoneId) return z;
          return {
            ...z,
            rules: z.rules.map((r) => (r.id === ruleId ? next : r)),
          };
        })
      );
    },
    []
  );

  const deleteRule = useCallback((zoneId: string, ruleId: string) => {
    setZones((prev) =>
      prev.map((z) => {
        if (z.id !== zoneId) return z;
        return { ...z, rules: z.rules.filter((r) => r.id !== ruleId) };
      })
    );
  }, []);

  // --- Persistence -----------------------------------------------------------

  const resetTo = useCallback((next: Zone[]) => {
    setZones(next);
    setBaseline(next);
    setMode({ kind: 'idle' });
  }, []);

  // --- Dirty check -----------------------------------------------------------

  const dirty = useMemo(() => {
    if (zones.length !== baseline.length) return true;
    // Compare by id + name + color + polygon + rules count.
    // Cheap because zone count is always small (≤50 typical).
    const byId = new Map(baseline.map((z) => [z.id, z]));
    for (const z of zones) {
      const b = byId.get(z.id);
      if (!b) return true;
      if (b.name !== z.name) return true;
      if (b.color !== z.color) return true;
      if (b.polygon.length !== z.polygon.length) return true;
      for (let i = 0; i < z.polygon.length; i++) {
        if (Math.abs(b.polygon[i].x - z.polygon[i].x) > 1e-6) return true;
        if (Math.abs(b.polygon[i].y - z.polygon[i].y) > 1e-6) return true;
      }
      // Rule content comparison. Cheap deep-equality via JSON.stringify
      // (rules are flat, deterministic-key objects — no Date/Map/Set
      // shenanigans, no problem). Order matters here — if the operator
      // reorders rules in the UI we treat that as dirty, but the current
      // UI doesn't reorder so this is just a safety net.
      if (b.rules.length !== z.rules.length) return true;
      for (let i = 0; i < z.rules.length; i++) {
        if (JSON.stringify(b.rules[i]) !== JSON.stringify(z.rules[i])) {
          return true;
        }
      }
    }
    return false;
  }, [zones, baseline]);

  return {
    zones,
    mode,
    dirty,
    startDrawing,
    addDraftVertex,
    finishDrawing,
    cancelDrawing,
    selectZone,
    clearSelection,
    patchSelected,
    moveVertex,
    deleteVertex,
    removeSelected,
    addRule,
    updateRule,
    deleteRule,
    resetTo,
  };
}

// Export type for components that introspect the mode
export type ZoneEditMode = EditMode;
