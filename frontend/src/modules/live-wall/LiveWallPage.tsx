import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Edit3, Eye, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Card } from '@/shared/components/Card';
import { Button } from '@/shared/components/Button';
import { Spinner } from '@/shared/components/Spinner';
import { useAuth } from '@/shared/hooks/useAuth';
import { CAMERA_STREAM_VIEW } from '@/shared/lib/permissions';
import { useCameras } from '@/modules/cameras/api';
import { useTrackEventStream } from '@/modules/tracks/useTrackEvents';
import { useUpdateWallPreset, useWallPresets } from '@/modules/live-wall/api';
import { WallGrid } from '@/modules/live-wall/WallGrid';
import { PresetManager } from '@/modules/live-wall/PresetManager';
import { NvencWarning } from '@/modules/live-wall/NvencWarning';
import { useNvencEstimate } from '@/modules/live-wall/useNvencEstimate';
import {
  LAYOUTS,
  type TileEntry,
  type WallPreset,
} from '@/modules/live-wall/types';

const LIVE_WALL_MANAGE_PRESETS = 'live_wall:manage_presets';

/**
 * Live Wall — multi-camera grid view with savable layout presets.
 *
 * State model:
 *   - `gridDims` (rows, cols)        local UI state, switches between LAYOUTS
 *   - `tiles`                         local UI state, rows*cols length
 *   - `activePreset`                  which saved preset is loaded, if any
 *   - `dirty`                         true if tiles diverge from activePreset
 *
 * When the user changes tiles, `dirty` flips on. They can save (update the
 * active preset) or save-as (create a new one).
 */
export default function LiveWallPage() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canView = hasPermission(CAMERA_STREAM_VIEW);
  const canManage = hasPermission(LIVE_WALL_MANAGE_PRESETS);

  const { data: cameras, isLoading: camerasLoading } = useCameras();
  const { data: presets, isLoading: presetsLoading } = useWallPresets();

  // Subscribe to live track events so overlays in tiles work.
  useTrackEventStream();

  const [editMode, setEditMode] = useState(false);
  const [gridDims, setGridDims] = useState<{ rows: number; cols: number }>({
    rows: 2,
    cols: 2,
  });
  const [tiles, setTiles] = useState<TileEntry[]>(() => Array(4).fill(null));
  const [activePreset, setActivePreset] = useState<WallPreset | null>(null);

  // Auto-load the default preset on first arrival, once data loads.
  useEffect(() => {
    if (!presets || presets.length === 0 || activePreset) return;
    const def = presets.find((p) => p.is_default) || presets[0];
    setGridDims({ rows: def.rows, cols: def.cols });
    setTiles(def.tiles);
    setActivePreset(def);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presets]);

  const dirty = useMemo(() => {
    if (!activePreset) {
      // No active preset — dirty only if any tile has a camera
      return tiles.some((t) => t !== null);
    }
    if (
      activePreset.rows !== gridDims.rows ||
      activePreset.cols !== gridDims.cols
    )
      return true;
    if (activePreset.tiles.length !== tiles.length) return true;
    for (let i = 0; i < tiles.length; i++) {
      if (activePreset.tiles[i] !== tiles[i]) return true;
    }
    return false;
  }, [activePreset, tiles, gridDims]);

  const update = useUpdateWallPreset(activePreset?.id || '');

  function changeLayout(rows: number, cols: number) {
    const newSize = rows * cols;
    setGridDims({ rows, cols });
    // Preserve existing assignments when growing; truncate when shrinking
    setTiles((prev) => {
      if (prev.length === newSize) return prev;
      if (prev.length < newSize) {
        return [...prev, ...Array(newSize - prev.length).fill(null)];
      }
      return prev.slice(0, newSize);
    });
  }

  function handleTileChange(index: number, cameraId: string | null) {
    setTiles((prev) => {
      const next = [...prev];
      // Prevent the same camera in two tiles — clear the previous slot first.
      if (cameraId) {
        for (let i = 0; i < next.length; i++) {
          if (next[i] === cameraId && i !== index) next[i] = null;
        }
      }
      next[index] = cameraId;
      return next;
    });
  }

  function handleTileSwap(fromIndex: number, toIndex: number) {
    setTiles((prev) => {
      const next = [...prev];
      const tmp = next[fromIndex];
      next[fromIndex] = next[toIndex];
      next[toIndex] = tmp;
      return next;
    });
  }

  // NVENC pressure estimate based on current assignment. Updates live as
  // tiles change so the operator sees the warning *before* saving.
  const nvenc = useNvencEstimate(tiles, cameras);

  function loadPreset(preset: WallPreset) {
    setGridDims({ rows: preset.rows, cols: preset.cols });
    setTiles(preset.tiles);
    setActivePreset(preset);
  }

  async function saveCurrent() {
    if (!activePreset) return;
    try {
      await update.mutateAsync({
        rows: gridDims.rows as 1 | 2 | 3 | 4,
        cols: gridDims.cols as 1 | 2 | 3 | 4,
        tiles,
      });
      toast.success(t('liveWall.presets.saved'));
      // Update the local activePreset snapshot so dirty flips back to false
      setActivePreset({
        ...activePreset,
        rows: gridDims.rows as 1 | 2 | 3 | 4,
        cols: gridDims.cols as 1 | 2 | 3 | 4,
        tiles,
      });
    } catch (err: any) {
      const raw = err?.response?.data?.detail;
      toast.error(typeof raw === 'string' ? raw : t('liveWall.presets.saveFailed'));
    }
  }

  if (!canView) {
    return (
      <Card className="p-8 text-center text-muted-foreground">
        {t('liveWall.noPermission')}
      </Card>
    );
  }

  if (camerasLoading || presetsLoading) {
    return (
      <Card className="flex items-center justify-center p-12">
        <Spinner size={24} />
      </Card>
    );
  }

  return (
    <div className="flex h-full flex-col gap-3">
      {/* Header — title + edit mode toggle */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            {t('nav.liveWall')}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t('liveWall.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {canManage && dirty && activePreset && (
            <Button
              variant="secondary"
              size="sm"
              onClick={saveCurrent}
              disabled={update.isPending}
            >
              {update.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              {t('liveWall.saveChanges')}
            </Button>
          )}
          {canManage && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setEditMode((v) => !v)}
            >
              {editMode ? (
                <>
                  <Eye className="h-4 w-4" />
                  {t('liveWall.viewMode')}
                </>
              ) : (
                <>
                  <Edit3 className="h-4 w-4" />
                  {t('liveWall.editMode')}
                </>
              )}
            </Button>
          )}
        </div>
      </div>

      {/* Layout selector + presets bar */}
      <Card className="space-y-3 p-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t('liveWall.layout')}
          </span>
          <div className="flex gap-1">
            {LAYOUTS.map((l) => (
              <button
                key={l.label}
                type="button"
                onClick={() => changeLayout(l.rows, l.cols)}
                disabled={!editMode && !!activePreset}
                className={
                  gridDims.rows === l.rows && gridDims.cols === l.cols
                    ? 'rounded-md bg-primary px-2.5 py-1 text-xs font-medium text-primary-foreground'
                    : 'rounded-md border border-border bg-surface px-2.5 py-1 text-xs hover:border-primary hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-50'
                }
              >
                {l.label}
              </button>
            ))}
          </div>
        </div>

        <PresetManager
          rows={gridDims.rows}
          cols={gridDims.cols}
          tiles={tiles}
          presets={presets || []}
          activePreset={activePreset}
          onLoadPreset={loadPreset}
          onCreated={(p) => setActivePreset(p)}
          canManage={canManage}
        />
      </Card>

      {/* NVENC pressure warning — shows when wall is configured to overload
          the consumer GPU's H.265 transcoding capacity. */}
      <NvencWarning estimate={nvenc} />

      {/* The grid itself */}
      <div className="min-h-0 flex-1">
        <WallGrid
          rows={gridDims.rows}
          cols={gridDims.cols}
          tiles={tiles}
          cameras={cameras || []}
          editable={editMode}
          onTileChange={handleTileChange}
          onTileSwap={handleTileSwap}
        />
      </div>
    </div>
  );
}
