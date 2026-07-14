import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Plus,
  Search,
  Video,
  Pencil,
  Trash2,
  MoreVertical,
  Play,
  Disc,
  MapPin,
  Crosshair,
} from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/shared/lib/cn';
import { Card } from '@/shared/components/Card';
import { Button } from '@/shared/components/Button';
import { Input } from '@/shared/components/Input';
import { Badge } from '@/shared/components/Badge';
import { Spinner } from '@/shared/components/Spinner';
import { Dialog } from '@/shared/components/Dialog';
import { useAuth } from '@/shared/hooks/useAuth';
import {
  CAMERA_CREATE,
  CAMERA_DELETE,
  CAMERA_STREAM_VIEW,
  CAMERA_UPDATE,
} from '@/shared/lib/permissions';
import { useCameras, useDeleteCamera } from '@/modules/cameras/api';
import { CameraFormDialog } from '@/modules/cameras/CameraFormDialog';
import { CameraCalibrationDialog } from '@/modules/cameras/CameraCalibrationDialog';
import { CameraLivePlayer } from '@/modules/cameras/CameraLivePlayer';
import { CameraActivityPanel } from '@/modules/cameras/CameraActivityPanel';
import { useTrackEventStream } from '@/modules/tracks/useTrackEvents';
import type { Camera, CameraStatus } from '@/shared/types/api';

const statusToneMap: Record<
  CameraStatus,
  { tone: 'success' | 'danger' | 'warning' | 'neutral'; pulse?: boolean }
> = {
  online: { tone: 'success', pulse: true },
  offline: { tone: 'danger' },
  error: { tone: 'danger' },
  pending: { tone: 'warning' },
  disabled: { tone: 'neutral' },
};

export default function CamerasPage() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const [search, setSearch] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingCamera, setEditingCamera] = useState<Camera | undefined>();
  const [previewingCamera, setPreviewingCamera] = useState<Camera | null>(null);
  const [calibratingCamera, setCalibratingCamera] = useState<Camera | null>(null);
  const [deletingCamera, setDeletingCamera] = useState<Camera | null>(null);

  const { data: cameras, isLoading } = useCameras({ search: search || undefined });
  const deleteMutation = useDeleteCamera();

  // Deep-link from elsewhere in the app: scroll the requested camera into
  // view and apply a brief highlight ring so the operator can find it.
  // Triggered via /cameras?focus=<cameraId>.
  const [searchParams, setSearchParams] = useSearchParams();
  const focusId = searchParams.get('focus');
  const [highlightedId, setHighlightedId] = useState<string | null>(null);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  useEffect(() => {
    if (!focusId || !cameras) return;
    const exists = cameras.some((c) => c.id === focusId);
    if (!exists) return;
    setHighlightedId(focusId);
    // Wait one frame so the card is mounted before scrolling.
    const id = requestAnimationFrame(() => {
      const el = cardRefs.current[focusId];
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    // Drop the highlight after a few seconds.
    const t = window.setTimeout(() => setHighlightedId(null), 2500);
    // Strip the query param so refresh doesn't re-trigger.
    const next = new URLSearchParams(searchParams);
    next.delete('focus');
    setSearchParams(next, { replace: true });
    return () => {
      cancelAnimationFrame(id);
      window.clearTimeout(t);
    };
  }, [focusId, cameras, searchParams, setSearchParams]);

  // Subscribe to live track events so the overlay buffer fills as soon
  // as the page mounts. Events are kept in a module-level buffer so they
  // persist across the preview dialog open/close cycle.
  useTrackEventStream();

  const canCreate = hasPermission(CAMERA_CREATE);
  const canUpdate = hasPermission(CAMERA_UPDATE);
  const canDelete = hasPermission(CAMERA_DELETE);
  const canView = hasPermission(CAMERA_STREAM_VIEW);

  function openAdd() {
    setEditingCamera(undefined);
    setFormOpen(true);
  }

  function openEdit(c: Camera) {
    setEditingCamera(c);
    setFormOpen(true);
  }

  async function confirmDelete() {
    if (!deletingCamera) return;
    try {
      await deleteMutation.mutateAsync(deletingCamera.id);
      toast.success(t('cameras.toast.deleted'));
      setDeletingCamera(null);
    } catch {
      toast.error(t('cameras.toast.deleteFailed'));
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            {t('nav.cameras')}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t('cameras.subtitle')}
          </p>
        </div>
        {canCreate && (
          <Button onClick={openAdd}>
            <Plus className="h-4 w-4" />
            {t('cameras.addButton')}
          </Button>
        )}
      </div>

      {/* Toolbar */}
      <Card className="p-3">
        <Input
          name="search"
          placeholder={t('cameras.searchPlaceholder')}
          leftIcon={<Search className="h-4 w-4" />}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </Card>

      {/* List */}
      {isLoading ? (
        <Card className="flex items-center justify-center p-12">
          <Spinner size={24} />
        </Card>
      ) : !cameras || cameras.length === 0 ? (
        <EmptyState canCreate={canCreate} onAdd={openAdd} />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {cameras.map((c) => (
            <CameraCard
              key={c.id}
              camera={c}
              canView={canView}
              canUpdate={canUpdate}
              canDelete={canDelete}
              highlighted={c.id === highlightedId}
              cardRef={(el) => {
                cardRefs.current[c.id] = el;
              }}
              onPreview={() => setPreviewingCamera(c)}
              onEdit={() => openEdit(c)}
              onCalibrate={() => setCalibratingCamera(c)}
              onDelete={() => setDeletingCamera(c)}
            />
          ))}
        </div>
      )}

      {/* Form dialog (add/edit) */}
      <CameraFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        camera={editingCamera}
      />

      {/* Calibration dialog */}
      {calibratingCamera && (
        <CameraCalibrationDialog
          camera={calibratingCamera}
          open={!!calibratingCamera}
          onOpenChange={(o) => !o && setCalibratingCamera(null)}
        />
      )}

      {/* Live preview dialog */}
      <Dialog
        open={!!previewingCamera}
        onOpenChange={(v) => !v && setPreviewingCamera(null)}
        size="lg"
        title={previewingCamera?.name || ''}
        description={previewingCamera?.description || undefined}
      >
        {previewingCamera && (
          <div className="space-y-3">
            <CameraLivePlayer
              hlsUrl={previewingCamera.hls_url}
              label={previewingCamera.mediamtx_path}
              cameraId={previewingCamera.id}
              className="aspect-video w-full"
            />
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span className="font-mono">{previewingCamera.mediamtx_path}</span>
              <StatusBadge status={previewingCamera.status} />
            </div>
          </div>
        )}
      </Dialog>

      {/* Delete confirmation */}
      <Dialog
        open={!!deletingCamera}
        onOpenChange={(v) => !v && setDeletingCamera(null)}
        size="sm"
        title={t('cameras.deleteTitle')}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => setDeletingCamera(null)}
              disabled={deleteMutation.isPending}
            >
              {t('common.cancel')}
            </Button>
            <Button
              variant="danger"
              onClick={confirmDelete}
              disabled={deleteMutation.isPending}
            >
              {t('common.delete')}
            </Button>
          </>
        }
      >
        <p className="text-sm text-foreground">
          {t('cameras.deleteConfirm', {
            name: deletingCamera?.name || '',
          })}
        </p>
      </Dialog>
    </div>
  );
}

// -- Camera card ----------------------------------------------------------------
function CameraCard({
  camera,
  canView,
  canUpdate,
  canDelete,
  highlighted,
  cardRef,
  onPreview,
  onEdit,
  onCalibrate,
  onDelete,
}: {
  camera: Camera;
  canView: boolean;
  canUpdate: boolean;
  canDelete: boolean;
  highlighted?: boolean;
  cardRef?: (el: HTMLDivElement | null) => void;
  onPreview: () => void;
  onEdit: () => void;
  onCalibrate: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div
      ref={cardRef}
      className={cn(
        'transition-shadow duration-300',
        highlighted && 'rounded-lg ring-2 ring-primary ring-offset-2 ring-offset-background'
      )}
    >
      <Card className="overflow-hidden">
      {/* Thumbnail / live preview area */}
      <div className="relative aspect-video bg-black/40">
        {canView && camera.status === 'online' ? (
          <CameraLivePlayer
            hlsUrl={camera.hls_url}
            label={camera.mediamtx_path}
            compact
            className="h-full w-full"
            autoPlay={false}
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <Video className="h-10 w-10 text-muted-foreground/40" />
          </div>
        )}
        <div className="absolute start-3 top-3">
          <StatusBadge status={camera.status} />
        </div>
        {camera.is_recording && (
          <div className="absolute end-3 top-3">
            <Badge tone="danger" dot pulse>
              <Disc className="h-3 w-3" />
              REC
            </Badge>
          </div>
        )}
        {canView && (
          <button
            type="button"
            onClick={onPreview}
            className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-opacity hover:bg-black/40 hover:opacity-100"
            aria-label={t('cameras.preview')}
          >
            <div className="rounded-full bg-primary/90 p-3">
              <Play className="h-5 w-5 text-primary-foreground" />
            </div>
          </button>
        )}
      </div>

      {/* Meta */}
      <div className="space-y-2 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <h3 className="truncate font-medium text-foreground">{camera.name}</h3>
            {camera.description && (
              <p className="mt-0.5 truncate text-xs text-muted-foreground">
                {camera.description}
              </p>
            )}
          </div>
          {(canUpdate || canDelete) && (
            <div className="relative">
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                aria-label="Open menu"
              >
                <MoreVertical className="h-4 w-4" />
              </button>
              {menuOpen && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setMenuOpen(false)}
                  />
                  <div className="absolute end-0 top-8 z-20 w-40 overflow-hidden rounded-md border border-border bg-surface shadow-xl">
                    {canUpdate && (
                      <button
                        type="button"
                        onClick={() => {
                          setMenuOpen(false);
                          onEdit();
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted"
                      >
                        <Pencil className="h-4 w-4" />
                        {t('common.edit')}
                      </button>
                    )}
                    {canUpdate && (
                      <button
                        type="button"
                        onClick={() => {
                          setMenuOpen(false);
                          onCalibrate();
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-sm text-foreground hover:bg-muted"
                      >
                        <Crosshair className="h-4 w-4" />
                        {t('cameras.calibration.action')}
                      </button>
                    )}
                    {canDelete && (
                      <button
                        type="button"
                        onClick={() => {
                          setMenuOpen(false);
                          onDelete();
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-sm text-danger hover:bg-danger/10"
                      >
                        <Trash2 className="h-4 w-4" />
                        {t('common.delete')}
                      </button>
                    )}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="font-mono">{camera.mediamtx_path}</span>
          <div className="flex items-center gap-2">
            <FloorPlanBadge camera={camera} />
            {camera.codec && (
              <Badge tone={camera.codec === 'H264' ? 'success' : 'warning'}>
                {camera.codec}
              </Badge>
            )}
            {camera.last_seen_at && (
              <span title={new Date(camera.last_seen_at).toLocaleString()}>
                {formatRelative(camera.last_seen_at)}
              </span>
            )}
          </div>
        </div>
      </div>
      <CameraActivityPanel cameraId={camera.id} online={camera.status === 'online'} />
    </Card>
    </div>
  );
}

function StatusBadge({ status }: { status: CameraStatus }) {
  const { t } = useTranslation();
  const cfg = statusToneMap[status];
  return (
    <Badge tone={cfg.tone} dot pulse={cfg.pulse}>
      {t(`cameras.status.${status}`)}
    </Badge>
  );
}

/**
 * Pin badge shown on a camera card when the camera is placed on one or
 * more floor plans. Click behavior:
 *   - 0 locations: not rendered
 *   - 1 location: jumps straight to the floor plan with marker pre-opened
 *   - 2+ locations: opens a small picker so the operator chooses which plan
 */
function FloorPlanBadge({ camera }: { camera: Camera }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [pickerOpen, setPickerOpen] = useState(false);
  const locations = camera.floor_plan_locations || [];

  if (locations.length === 0) return null;

  function jumpTo(planId: string, markerId: string) {
    navigate(`/floor-plan?preview=${planId}&openMarker=${markerId}`);
  }

  if (locations.length === 1) {
    const loc = locations[0];
    return (
      <button
        type="button"
        onClick={() => jumpTo(loc.plan_id, loc.marker_id)}
        title={t('cameras.row.onFloorPlan', { name: loc.plan_name })}
        className="flex items-center gap-1 rounded-md border border-border bg-surface px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground hover:border-primary hover:text-primary"
      >
        <MapPin className="h-3 w-3" />
        <span className="hidden sm:inline">1</span>
      </button>
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setPickerOpen((v) => !v)}
        title={t('cameras.row.onNFloorPlans', { count: locations.length })}
        className="flex items-center gap-1 rounded-md border border-border bg-surface px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground hover:border-primary hover:text-primary"
      >
        <MapPin className="h-3 w-3" />
        <span>{locations.length}</span>
      </button>
      {pickerOpen && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setPickerOpen(false)}
          />
          <div className="absolute end-0 top-7 z-20 w-56 overflow-hidden rounded-md border border-border bg-surface shadow-xl">
            <div className="border-b border-border px-3 py-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
              {t('cameras.row.pickPlan')}
            </div>
            {locations.map((loc) => (
              <button
                key={loc.marker_id}
                type="button"
                onClick={() => {
                  setPickerOpen(false);
                  jumpTo(loc.plan_id, loc.marker_id);
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-start text-sm text-foreground hover:bg-muted"
              >
                <MapPin className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
                <span className="truncate">{loc.plan_name}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function EmptyState({
  canCreate,
  onAdd,
}: {
  canCreate: boolean;
  onAdd: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Card className="flex flex-col items-center justify-center gap-3 p-12 text-center">
      <div className="rounded-full bg-muted p-3">
        <Video className="h-7 w-7 text-muted-foreground" />
      </div>
      <div>
        <h3 className="font-medium text-foreground">{t('cameras.emptyTitle')}</h3>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          {t('cameras.emptyHint')}
        </p>
      </div>
      {canCreate && (
        <Button onClick={onAdd}>
          <Plus className="h-4 w-4" />
          {t('cameras.addButton')}
        </Button>
      )}
    </Card>
  );
}

function formatRelative(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}
