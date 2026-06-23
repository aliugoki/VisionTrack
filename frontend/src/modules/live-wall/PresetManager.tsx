import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Save, Star, Trash2, Loader2, BookmarkPlus } from 'lucide-react';
import { toast } from 'sonner';
import { Dialog } from '@/shared/components/Dialog';
import { Input } from '@/shared/components/Input';
import { Button } from '@/shared/components/Button';
import {
  useCreateWallPreset,
  useDeleteWallPreset,
  useUpdateWallPreset,
} from '@/modules/live-wall/api';
import type {
  TileEntry,
  WallPreset,
} from '@/modules/live-wall/types';

interface PresetManagerProps {
  /** Current grid state being edited. */
  rows: number;
  cols: number;
  tiles: TileEntry[];
  /** All presets in the tenant. */
  presets: WallPreset[];
  /** Currently selected preset, if any (we're editing it vs creating new). */
  activePreset: WallPreset | null;
  /** Called when the user picks a preset from the list. */
  onLoadPreset: (preset: WallPreset) => void;
  /** Called after a successful create — give caller the new preset to select. */
  onCreated: (preset: WallPreset) => void;
  /** Whether the current user can modify presets. */
  canManage: boolean;
}

export function PresetManager({
  rows,
  cols,
  tiles,
  presets,
  activePreset,
  onLoadPreset,
  onCreated,
  canManage,
}: PresetManagerProps) {
  const { t } = useTranslation();
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [deletingPreset, setDeletingPreset] = useState<WallPreset | null>(null);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {presets.length === 0 ? (
          <span className="text-xs text-muted-foreground">
            {t('liveWall.presets.empty')}
          </span>
        ) : (
          presets.map((p) => (
            <PresetChip
              key={p.id}
              preset={p}
              active={activePreset?.id === p.id}
              onSelect={() => onLoadPreset(p)}
              onDelete={() => setDeletingPreset(p)}
              canManage={canManage}
            />
          ))
        )}

        {canManage && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setSaveDialogOpen(true)}
          >
            <BookmarkPlus className="h-4 w-4" />
            {t('liveWall.presets.saveAs')}
          </Button>
        )}
      </div>

      <SavePresetDialog
        open={saveDialogOpen}
        onOpenChange={setSaveDialogOpen}
        rows={rows}
        cols={cols}
        tiles={tiles}
        onCreated={(p) => {
          setSaveDialogOpen(false);
          onCreated(p);
        }}
      />

      <DeletePresetDialog
        preset={deletingPreset}
        onOpenChange={(v) => !v && setDeletingPreset(null)}
      />
    </div>
  );
}

// -- preset chip --------------------------------------------------------------
function PresetChip({
  preset,
  active,
  onSelect,
  onDelete,
  canManage,
}: {
  preset: WallPreset;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
  canManage: boolean;
}) {
  return (
    <div
      className={
        active
          ? 'inline-flex items-center gap-1 rounded-full bg-primary px-3 py-1 text-xs font-medium text-primary-foreground'
          : 'inline-flex items-center gap-1 rounded-full border border-border bg-surface px-3 py-1 text-xs hover:border-primary hover:bg-primary/5'
      }
    >
      <button
        type="button"
        onClick={onSelect}
        className="flex items-center gap-1.5"
      >
        {preset.is_default && <Star className="h-3 w-3" />}
        <span>{preset.name}</span>
        <span className="opacity-60">
          ({preset.rows}×{preset.cols})
        </span>
      </button>
      {canManage && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className={
            active
              ? 'ms-1 rounded-full p-0.5 hover:bg-primary-foreground/20'
              : 'ms-1 rounded-full p-0.5 text-muted-foreground hover:bg-muted hover:text-danger'
          }
          aria-label="Delete preset"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}

// -- save dialog --------------------------------------------------------------
function SavePresetDialog({
  open,
  onOpenChange,
  rows,
  cols,
  tiles,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  rows: number;
  cols: number;
  tiles: TileEntry[];
  onCreated: (p: WallPreset) => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isDefault, setIsDefault] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const create = useCreateWallPreset();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim()) {
      setError(t('liveWall.presets.nameRequired'));
      return;
    }
    try {
      const preset = await create.mutateAsync({
        name: name.trim(),
        description: description.trim() || null,
        rows: rows as 1 | 2 | 3 | 4,
        cols: cols as 1 | 2 | 3 | 4,
        tiles,
        is_default: isDefault,
      });
      toast.success(t('liveWall.presets.saved'));
      setName('');
      setDescription('');
      setIsDefault(false);
      onCreated(preset);
    } catch (err: any) {
      const raw = err?.response?.data?.detail;
      setError(typeof raw === 'string' ? raw : t('liveWall.presets.saveFailed'));
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('liveWall.presets.saveTitle')}
      description={t('liveWall.presets.saveSubtitle')}
      size="sm"
      footer={
        <>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={create.isPending}
          >
            {t('common.cancel')}
          </Button>
          <Button onClick={onSubmit} disabled={create.isPending}>
            {create.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            <Save className="h-4 w-4" />
            {t('common.save')}
          </Button>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-3" id="preset-form">
        <Input
          label={t('liveWall.presets.name')}
          name="name"
          required
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Input
          label={t('liveWall.presets.description')}
          name="description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
            className="h-4 w-4 rounded border-input bg-surface text-primary focus:ring-2 focus:ring-ring"
          />
          <span className="text-sm">
            {t('liveWall.presets.makeDefault')}
          </span>
        </label>
        {error && (
          <div className="rounded-md border border-danger/30 bg-danger/10 p-2 text-xs text-danger">
            {error}
          </div>
        )}
      </form>
    </Dialog>
  );
}

// -- delete dialog ------------------------------------------------------------
function DeletePresetDialog({
  preset,
  onOpenChange,
}: {
  preset: WallPreset | null;
  onOpenChange: (v: boolean) => void;
}) {
  const { t } = useTranslation();
  const remove = useDeleteWallPreset();

  async function confirm() {
    if (!preset) return;
    try {
      await remove.mutateAsync(preset.id);
      toast.success(t('liveWall.presets.deleted'));
      onOpenChange(false);
    } catch {
      toast.error(t('liveWall.presets.deleteFailed'));
    }
  }

  return (
    <Dialog
      open={!!preset}
      onOpenChange={onOpenChange}
      size="sm"
      title={t('liveWall.presets.deleteTitle')}
      footer={
        <>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={remove.isPending}
          >
            {t('common.cancel')}
          </Button>
          <Button
            variant="danger"
            onClick={confirm}
            disabled={remove.isPending}
          >
            {t('common.delete')}
          </Button>
        </>
      }
    >
      <p className="text-sm">
        {t('liveWall.presets.deleteConfirm', { name: preset?.name || '' })}
      </p>
    </Dialog>
  );
}
