import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { FileText, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/shared/components/Button';
import { Card } from '@/shared/components/Card';
import { Spinner } from '@/shared/components/Spinner';
import { Dialog } from '@/shared/components/Dialog';
import { Input } from '@/shared/components/Input';
import { useAuth } from '@/shared/hooks/useAuth';
import { useSites } from '@/modules/sites/api';
import { useCameras } from '@/modules/cameras/api';
import {
  useDeleteFloorPlan,
  useFloorPlans,
  useUpdateFloorPlan,
} from '@/modules/floor-plan/api';
import { FloorPlanCard } from '@/modules/floor-plan/FloorPlanCard';
import { FloorPlanUploadDialog } from '@/modules/floor-plan/FloorPlanUploadDialog';
import { FloorPlanViewer } from '@/modules/floor-plan/FloorPlanViewer';
import { MarkerLayer } from '@/modules/floor-plan/MarkerLayer';
import { MarkerLivePreview } from '@/modules/floor-plan/MarkerLivePreview';
import { ZonePolygonLayer } from '@/modules/floor-plan/ZonePolygonLayer';
import type { FloorPlan } from '@/modules/floor-plan/types';
import type { Camera } from '@/shared/types/api';

const FLOOR_PLAN_READ = 'floor_plan:read';
const FLOOR_PLAN_CREATE = 'floor_plan:create';
const FLOOR_PLAN_UPDATE = 'floor_plan:update';
const FLOOR_PLAN_DELETE = 'floor_plan:delete';

export default function FloorPlansPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const canRead = hasPermission(FLOOR_PLAN_READ);
  const canCreate = hasPermission(FLOOR_PLAN_CREATE);
  const canUpdate = hasPermission(FLOOR_PLAN_UPDATE);
  const canDelete = hasPermission(FLOOR_PLAN_DELETE);

  const { data: plans, isLoading } = useFloorPlans();
  const { data: sites } = useSites();
  const { data: cameras } = useCameras();

  const sitesById = useMemo(() => {
    const map = new Map<string, (typeof sites extends Array<infer T> ? T : never)>();
    for (const s of sites || []) map.set(s.id, s);
    return map;
  }, [sites]);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [previewing, setPreviewing] = useState<FloorPlan | null>(null);
  const [editing, setEditing] = useState<FloorPlan | null>(null);
  const [deleting, setDeleting] = useState<FloorPlan | null>(null);
  // Marker to auto-open in the live-preview popover when the dialog mounts.
  // Set by deep-links from the Cameras page (?preview=<plan>&openMarker=<id>).
  const [initialMarkerId, setInitialMarkerId] = useState<string | null>(null);

  // Deep-link support: if ?preview=<planId>&openMarker=<markerId> is present,
  // auto-open the preview dialog with that plan + auto-open the popover.
  const [searchParams, setSearchParams] = useSearchParams();
  useEffect(() => {
    if (!plans) return;
    const previewId = searchParams.get('preview');
    const markerId = searchParams.get('openMarker');
    if (!previewId) return;
    const plan = plans.find((p) => p.id === previewId);
    if (!plan) return;
    setPreviewing(plan);
    setInitialMarkerId(markerId);
    // Strip params so refresh doesn't re-trigger; replace history entry
    // to keep the back button useful.
    const next = new URLSearchParams(searchParams);
    next.delete('preview');
    next.delete('openMarker');
    setSearchParams(next, { replace: true });
  }, [plans, searchParams, setSearchParams]);

  if (!canRead) {
    return (
      <Card className="p-8 text-center text-muted-foreground">
        {t('floorPlan.noPermission')}
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            {t('nav.floorPlan')}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t('floorPlan.subtitle')}
          </p>
        </div>
        {canCreate && (
          <Button onClick={() => setUploadOpen(true)}>
            <Plus className="h-4 w-4" />
            {t('floorPlan.upload.submit')}
          </Button>
        )}
      </div>

      {isLoading ? (
        <Card className="flex items-center justify-center p-12">
          <Spinner size={24} />
        </Card>
      ) : !plans || plans.length === 0 ? (
        <Card className="flex flex-col items-center justify-center gap-3 p-12 text-center">
          <FileText className="h-12 w-12 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">
            {t('floorPlan.empty')}
          </p>
          {canCreate && (
            <Button variant="secondary" onClick={() => setUploadOpen(true)}>
              <Plus className="h-4 w-4" />
              {t('floorPlan.upload.submit')}
            </Button>
          )}
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {plans.map((plan) => (
            <FloorPlanCard
              key={plan.id}
              plan={plan}
              site={sitesById.get(plan.site_id) as any}
              canEdit={canUpdate}
              canDelete={canDelete}
              onPreview={() => setPreviewing(plan)}
              onEdit={() => setEditing(plan)}
              onEditPlacement={() => navigate(`/floor-plan/edit/${plan.id}`)}
              onDelete={() => setDeleting(plan)}
            />
          ))}
        </div>
      )}

      {/* Upload dialog */}
      <FloorPlanUploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
      />

      {/* Preview dialog */}
      {/* Preview dialog — interactive: click any marker to see its live feed */}
      <Dialog
        open={!!previewing}
        onOpenChange={(v) => {
          if (!v) {
            setPreviewing(null);
            setInitialMarkerId(null);
          }
        }}
        title={previewing?.name || ''}
        description={previewing?.description || undefined}
        size="xl"
      >
        {previewing && (
          <div className="h-[70vh]">
            <InteractivePreview
              plan={previewing}
              cameras={cameras || []}
              initialMarkerId={initialMarkerId}
            />
          </div>
        )}
      </Dialog>

      {/* Edit dialog */}
      <FloorPlanEditDialog
        plan={editing}
        onOpenChange={(v) => !v && setEditing(null)}
      />

      {/* Delete confirmation */}
      <FloorPlanDeleteDialog
        plan={deleting}
        onOpenChange={(v) => !v && setDeleting(null)}
      />
    </div>
  );
}

// -- edit dialog --------------------------------------------------------------
function FloorPlanEditDialog({
  plan,
  onOpenChange,
}: {
  plan: FloorPlan | null;
  onOpenChange: (v: boolean) => void;
}) {
  const { t } = useTranslation();
  const update = useUpdateFloorPlan(plan?.id || '');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  // Sync state when the editing plan changes
  useEffect(() => {
    if (plan) {
      setName(plan.name);
      setDescription(plan.description || '');
    }
  }, [plan]);

  if (!plan) return null;

  async function save() {
    if (!plan) return;
    try {
      await update.mutateAsync({
        name: name.trim() || plan.name,
        description: description.trim() || null,
      });
      toast.success(t('floorPlan.editToast.updated'));
      onOpenChange(false);
    } catch {
      toast.error(t('floorPlan.editToast.failed'));
    }
  }

  return (
    <Dialog
      open={!!plan}
      onOpenChange={onOpenChange}
      title={t('floorPlan.edit.title')}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button onClick={save} disabled={update.isPending}>
            {t('common.save')}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Input
          label={t('floorPlan.upload.name')}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <Input
          label={t('floorPlan.upload.description')}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
    </Dialog>
  );
}

// -- delete dialog ------------------------------------------------------------
function FloorPlanDeleteDialog({
  plan,
  onOpenChange,
}: {
  plan: FloorPlan | null;
  onOpenChange: (v: boolean) => void;
}) {
  const { t } = useTranslation();
  const remove = useDeleteFloorPlan();

  async function confirm() {
    if (!plan) return;
    try {
      await remove.mutateAsync(plan.id);
      toast.success(t('floorPlan.deleteToast.success'));
      onOpenChange(false);
    } catch {
      toast.error(t('floorPlan.deleteToast.failed'));
    }
  }

  return (
    <Dialog
      open={!!plan}
      onOpenChange={onOpenChange}
      size="sm"
      title={t('floorPlan.delete.title')}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button variant="danger" onClick={confirm} disabled={remove.isPending}>
            {t('common.delete')}
          </Button>
        </>
      }
    >
      <p className="text-sm">
        {t('floorPlan.delete.confirm', { name: plan?.name || '' })}
      </p>
    </Dialog>
  );
}

// -- interactive preview ------------------------------------------------------

function InteractivePreview({
  plan,
  cameras,
  initialMarkerId,
}: {
  plan: FloorPlan;
  cameras: Camera[];
  initialMarkerId?: string | null;
}) {
  // Selected marker = the one currently showing a live preview popover.
  // Initialized from the deep-link param if it points at a real marker.
  const [previewMarkerId, setPreviewMarkerId] = useState<string | null>(
    initialMarkerId &&
      plan.markers?.some((m) => m.id === initialMarkerId)
      ? initialMarkerId
      : null
  );
  const previewMarker = useMemo(
    () =>
      previewMarkerId
        ? plan.markers?.find((m) => m.id === previewMarkerId) || null
        : null,
    [previewMarkerId, plan.markers]
  );
  const previewCamera = previewMarker
    ? cameras.find((c) => c.id === previewMarker.camera_id)
    : undefined;

  return (
    <FloorPlanViewer plan={plan}>
      {({ currentScale }) => (
        <>
          {/* Zones — read-only context behind the markers */}
          <ZonePolygonLayer
            zones={plan.zones || []}
            selectedZoneId={null}
            draftPoints={null}
            draftColor={null}
            editable={false}
            currentScale={currentScale}
            imageWidthPx={plan.width_px}
            imageHeightPx={plan.height_px}
            // No-op handlers — viewer mode is read-only
            onSelectZone={() => {}}
            onMoveVertex={() => {}}
            onDeleteVertex={() => {}}
          />
          <MarkerLayer
            markers={plan.markers || []}
            cameras={cameras}
            selectedMarkerId={previewMarkerId}
            editable={false}
            currentScale={currentScale}
            imageWidthPx={plan.width_px}
            imageHeightPx={plan.height_px}
            // In viewer mode these handlers are no-ops; click goes to
            // onClickMarker below.
            onSelectMarker={() => {}}
            onMoveMarker={() => {}}
            onRemoveSelected={() => {}}
            onClickMarker={setPreviewMarkerId}
          />
          {previewMarker && (
            <MarkerLivePreview
              marker={previewMarker}
              camera={previewCamera}
              imageWidthPx={plan.width_px}
              imageHeightPx={plan.height_px}
              onClose={() => setPreviewMarkerId(null)}
            />
          )}
        </>
      )}
    </FloorPlanViewer>
  );
}
