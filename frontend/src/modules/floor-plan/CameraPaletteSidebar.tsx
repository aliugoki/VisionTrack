import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Camera as CameraIcon,
  MapPin,
  Plus,
  RotateCw,
  Video,
  X,
} from 'lucide-react';
import { cn } from '@/shared/lib/cn';
import type { Camera } from '@/shared/types/api';
import type { FloorPlanMarker } from '@/modules/floor-plan/types';
import { DEFAULT_CONE } from '@/modules/floor-plan/types';

interface CameraPaletteSidebarProps {
  cameras: Camera[];
  markers: FloorPlanMarker[];
  placingCameraId: string | null;
  selectedMarkerId: string | null;
  onPickForPlacement: (cameraId: string) => void;
  onSelectMarker: (markerId: string) => void;
  onRemoveSelected: () => void;
  onCancel: () => void;
  /** Patch any field on a marker — used by the cone-properties panel. */
  onPatchMarker: (markerId: string, patch: Partial<FloorPlanMarker>) => void;
}

/**
 * Right-side sidebar in the editor — pick cameras to place, see what's
 * already placed. Single scrollable column to avoid flex-1 fighting
 * between sections when parent height is constrained.
 */
export function CameraPaletteSidebar({
  cameras,
  markers,
  placingCameraId,
  selectedMarkerId,
  onPickForPlacement,
  onSelectMarker,
  onRemoveSelected,
  onCancel,
  onPatchMarker,
}: CameraPaletteSidebarProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { placed, unplaced } = useMemo(() => {
    const placedIds = new Set(markers.map((m) => m.camera_id));
    return {
      placed: markers,
      unplaced: cameras.filter((c) => !placedIds.has(c.id)),
    };
  }, [cameras, markers]);

  const camerasById = useMemo(() => {
    const map = new Map<string, Camera>();
    for (const c of cameras) map.set(c.id, c);
    return map;
  }, [cameras]);

  // The selected marker (if any) — drives the cone properties panel.
  const selectedMarker = useMemo(
    () =>
      selectedMarkerId
        ? markers.find((m) => m.id === selectedMarkerId) || null
        : null,
    [markers, selectedMarkerId]
  );

  return (
    <aside className="flex h-full w-72 flex-shrink-0 flex-col overflow-hidden border-s border-border bg-surface">
      {/* Placing-mode banner — solid primary so it's impossible to miss */}
      {placingCameraId && (
        <div
          className="flex-shrink-0 border-b-2 border-primary bg-primary px-3 py-3 text-sm text-primary-foreground"
          style={{ minHeight: '64px' }}
        >
          <div className="flex items-start gap-2">
            <Plus className="mt-0.5 h-4 w-4 flex-shrink-0" />
            <div className="min-w-0 flex-1">
              <p className="font-semibold">
                {t('floorPlan.editor.placingMode', {
                  name: camerasById.get(placingCameraId)?.name || 'camera',
                })}
              </p>
              <p className="mt-0.5 text-xs opacity-90">
                {t('floorPlan.editor.placingHint')}
              </p>
            </div>
            <button
              type="button"
              onClick={onCancel}
              className="flex-shrink-0 rounded p-0.5 hover:bg-primary-foreground/20"
              aria-label={t('common.cancel')}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* Single scrollable column containing both sections */}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        {/* Unplaced cameras section */}
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t('floorPlan.editor.unplaced', { count: unplaced.length })}
        </h3>
        {cameras.length === 0 ? (
          <p className="mb-4 text-xs text-muted-foreground">
            {t('floorPlan.editor.noCameras')}
          </p>
        ) : unplaced.length === 0 ? (
          <p className="mb-4 text-xs text-muted-foreground">
            {t('floorPlan.editor.unplacedEmpty')}
          </p>
        ) : (
          <ul className="mb-4 space-y-0.5">
            {unplaced.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => onPickForPlacement(c.id)}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-sm transition-colors',
                    placingCameraId === c.id
                      ? 'bg-primary text-primary-foreground'
                      : 'hover:bg-muted'
                  )}
                >
                  <CameraIcon className="h-3.5 w-3.5 flex-shrink-0" />
                  <span className="truncate">{c.name}</span>
                  <span
                    className={cn(
                      'ms-auto h-1.5 w-1.5 flex-shrink-0 rounded-full',
                      c.status === 'online'
                        ? 'bg-success'
                        : 'bg-muted-foreground'
                    )}
                  />
                </button>
              </li>
            ))}
          </ul>
        )}

        {/* Divider */}
        <div className="my-3 border-t border-border" />

        {/* Placed markers section */}
        <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t('floorPlan.editor.placed', { count: placed.length })}
        </h3>
        {placed.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            {t('floorPlan.editor.placedEmpty')}
          </p>
        ) : (
          <ul className="space-y-0.5">
            {placed.map((m) => {
              const cam = camerasById.get(m.camera_id);
              const isSel = m.id === selectedMarkerId;
              return (
                <li
                  key={m.id}
                  className={cn(
                    'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm',
                    isSel
                      ? 'bg-primary text-primary-foreground'
                      : 'hover:bg-muted'
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelectMarker(m.id)}
                    className="flex min-w-0 flex-1 items-center gap-2 text-start"
                  >
                    <MapPin className="h-3.5 w-3.5 flex-shrink-0" />
                    <span className="truncate">
                      {m.label || cam?.name || 'Unknown'}
                    </span>
                  </button>
                  {isSel && (
                    <>
                      <button
                        type="button"
                        onClick={() => navigate(`/cameras?focus=${m.camera_id}`)}
                        className="flex-shrink-0 rounded p-0.5 hover:bg-primary-foreground/20"
                        aria-label={t('floorPlan.editor.goToCamera')}
                        title={t('floorPlan.editor.goToCamera')}
                      >
                        <Video className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={onRemoveSelected}
                        className="flex-shrink-0 rounded p-0.5 hover:bg-primary-foreground/20"
                        aria-label={t('common.remove')}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        )}

        {/* Coverage cone panel — visible when a marker is selected */}
        {selectedMarker && (
          <ConePanel
            marker={selectedMarker}
            onPatch={(patch) => onPatchMarker(selectedMarker.id, patch)}
          />
        )}
      </div>
    </aside>
  );
}

// -- coverage cone properties panel ------------------------------------------
function ConePanel({
  marker,
  onPatch,
}: {
  marker: FloorPlanMarker;
  onPatch: (patch: Partial<FloorPlanMarker>) => void;
}) {
  const { t } = useTranslation();
  const enabled =
    marker.cone_angle_deg != null &&
    marker.cone_range != null &&
    marker.cone_rotation_deg != null;

  function toggle() {
    if (enabled) {
      // Disable: clear all three to null
      onPatch({
        cone_angle_deg: null,
        cone_range: null,
        cone_rotation_deg: null,
      });
    } else {
      // Enable: set defaults
      onPatch({ ...DEFAULT_CONE });
    }
  }

  return (
    <div className="mt-4 border-t border-border pt-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {t('floorPlan.editor.cone.title')}
        </h3>
        <label className="flex cursor-pointer items-center gap-1.5 text-xs">
          <input
            type="checkbox"
            checked={enabled}
            onChange={toggle}
            className="h-3.5 w-3.5"
          />
          <span className="text-muted-foreground">
            {t('floorPlan.editor.cone.show')}
          </span>
        </label>
      </div>

      {!enabled ? (
        <p className="text-xs text-muted-foreground">
          {t('floorPlan.editor.cone.disabledHint')}
        </p>
      ) : (
        <div className="space-y-3">
          {/* Angle slider */}
          <div>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                {t('floorPlan.editor.cone.angle')}
              </span>
              <span className="font-mono text-foreground">
                {marker.cone_angle_deg?.toFixed(0)}°
              </span>
            </div>
            <input
              type="range"
              min={10}
              max={360}
              step={5}
              value={marker.cone_angle_deg ?? 90}
              onChange={(e) =>
                onPatch({ cone_angle_deg: Number(e.target.value) })
              }
              className="w-full"
            />
          </div>

          {/* Range slider — shown as percentage of plan width */}
          <div>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                {t('floorPlan.editor.cone.range')}
              </span>
              <span className="font-mono text-foreground">
                {((marker.cone_range ?? 0) * 100).toFixed(0)}%
              </span>
            </div>
            <input
              type="range"
              min={0.02}
              max={1}
              step={0.01}
              value={marker.cone_range ?? 0.15}
              onChange={(e) =>
                onPatch({ cone_range: Number(e.target.value) })
              }
              className="w-full"
            />
          </div>

          {/* Rotation slider with quick-set buttons */}
          <div>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                {t('floorPlan.editor.cone.rotation')}
              </span>
              <span className="font-mono text-foreground">
                {marker.cone_rotation_deg?.toFixed(0)}°
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={359}
              step={5}
              value={marker.cone_rotation_deg ?? 0}
              onChange={(e) =>
                onPatch({ cone_rotation_deg: Number(e.target.value) })
              }
              className="w-full"
            />
            {/* Quick-set buttons for cardinal directions */}
            <div className="mt-1 grid grid-cols-4 gap-1">
              {[
                { label: t('floorPlan.editor.cone.dirRight'), deg: 0 },
                { label: t('floorPlan.editor.cone.dirDown'), deg: 90 },
                { label: t('floorPlan.editor.cone.dirLeft'), deg: 180 },
                { label: t('floorPlan.editor.cone.dirUp'), deg: 270 },
              ].map((opt) => (
                <button
                  key={opt.deg}
                  type="button"
                  onClick={() => onPatch({ cone_rotation_deg: opt.deg })}
                  className={cn(
                    'rounded px-1 py-0.5 text-xs',
                    marker.cone_rotation_deg === opt.deg
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-muted text-muted-foreground hover:bg-muted/70'
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Reset button */}
          <button
            type="button"
            onClick={() => onPatch({ ...DEFAULT_CONE })}
            className="flex w-full items-center justify-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <RotateCw className="h-3 w-3" />
            {t('floorPlan.editor.cone.reset')}
          </button>
        </div>
      )}
    </div>
  );
}
