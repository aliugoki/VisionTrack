import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, CheckCheck, Loader2, Save } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/shared/components/Button';
import { Card } from '@/shared/components/Card';
import { Spinner } from '@/shared/components/Spinner';
import { useAuth } from '@/shared/hooks/useAuth';
import { useCameras } from '@/modules/cameras/api';
import {
  useFloorPlan,
  useUpdateFloorPlanMarkers,
  useUpdateFloorPlanZones,
} from '@/modules/floor-plan/api';
import { FloorPlanViewer } from '@/modules/floor-plan/FloorPlanViewer';
import { MarkerLayer } from '@/modules/floor-plan/MarkerLayer';
import { CameraPaletteSidebar } from '@/modules/floor-plan/CameraPaletteSidebar';
import { useMarkerEditing } from '@/modules/floor-plan/useMarkerEditing';
import { ZonePolygonLayer } from '@/modules/floor-plan/ZonePolygonLayer';
import { ZonePaletteSidebar } from '@/modules/floor-plan/ZonePaletteSidebar';
import { useZoneEditing } from '@/modules/floor-plan/useZoneEditing';
import {
  EditorSidebarTabs,
  type SidebarTab,
} from '@/modules/floor-plan/EditorSidebarTabs';

const FLOOR_PLAN_UPDATE = 'floor_plan:update';
const ZONE_UPDATE = 'zone:update';

/**
 * Full-page floor-plan editor.
 *
 * URL: /floor-plan/edit/:planId
 *
 * Layout: viewer on the left fills available space; tabbed sidebar on
 * the right is a fixed 288px (w-72). Header has back + save buttons.
 *
 * Two editing modes coexist:
 *   - Cameras tab → MarkerLayer + CameraPaletteSidebar (Batch D/E features)
 *   - Zones tab   → ZonePolygonLayer + ZonePaletteSidebar (Step 5 Batch B)
 *
 * Switching tabs doesn't lose unsaved work in the other tab. The Save
 * button persists whichever section is dirty (or both, in sequence).
 */
export default function FloorPlanEditPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { planId } = useParams<{ planId: string }>();
  const { hasPermission } = useAuth();
  const canEditMarkers = hasPermission(FLOOR_PLAN_UPDATE);
  const canEditZones = hasPermission(ZONE_UPDATE);

  const { data: plan, isLoading } = useFloorPlan(planId);
  const { data: cameras } = useCameras();
  const updateMarkers = useUpdateFloorPlanMarkers(planId || '');
  const updateZones = useUpdateFloorPlanZones(planId || '');

  const markerEditor = useMarkerEditing([]);
  const zoneEditor = useZoneEditing([]);

  // Active sidebar tab — defaults to Cameras for backward compat with how
  // operators used the editor in Step 4.
  const [activeTab, setActiveTab] = useState<SidebarTab>('cameras');

  // Load initial state when the plan loads
  useEffect(() => {
    if (plan) {
      markerEditor.resetTo(plan.markers || []);
      zoneEditor.resetTo(plan.zones || []);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan?.id]);

  // ESC cancels in-progress zone drawing
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && zoneEditor.mode.kind === 'drawing') {
        zoneEditor.cancelDrawing();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [zoneEditor]);

  // Combined dirty flag — either editor could have unsaved work
  const dirty = markerEditor.dirty || zoneEditor.dirty;
  const saving = updateMarkers.isPending || updateZones.isPending;

  // Prompt before navigating away with unsaved changes
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirty]);

  async function handleSave() {
    if (!planId) return;
    try {
      // Sequential save: a failure on one section won't leave the other
      // in an inconsistent client/server state.
      if (markerEditor.dirty) {
        await updateMarkers.mutateAsync(markerEditor.markers);
        markerEditor.resetTo(markerEditor.markers);
      }
      if (zoneEditor.dirty) {
        await updateZones.mutateAsync(zoneEditor.zones);
        zoneEditor.resetTo(zoneEditor.zones);
      }
      toast.success(t('floorPlan.editor.saved'));
    } catch (err: any) {
      const raw = err?.response?.data?.detail;
      toast.error(
        typeof raw === 'string' ? raw : t('floorPlan.editor.saveFailed')
      );
    }
  }

  function handleBack() {
    if (dirty) {
      if (!window.confirm(t('floorPlan.editor.discardConfirm'))) return;
    }
    navigate('/floor-plan');
  }

  // If user lacks BOTH edit permissions, deny outright. If they have one
  // but not the other, the lacking tab simply becomes read-only.
  if (!canEditMarkers && !canEditZones) {
    return (
      <Card className="p-8 text-center text-muted-foreground">
        {t('floorPlan.editor.noPermission')}
      </Card>
    );
  }

  if (isLoading || !plan) {
    return (
      <Card className="flex items-center justify-center p-12">
        <Spinner size={24} />
      </Card>
    );
  }

  const placingCameraId =
    markerEditor.mode.kind === 'placing' ? markerEditor.mode.cameraId : null;
  const selectedMarkerId =
    markerEditor.mode.kind === 'selected' ? markerEditor.mode.markerId : null;
  const selectedZoneId =
    zoneEditor.mode.kind === 'selected' ? zoneEditor.mode.zoneId : null;
  const drawingZone = zoneEditor.mode.kind === 'drawing';
  const draftPoints = drawingZone ? zoneEditor.mode.draftPoints : null;
  const draftColor = drawingZone ? zoneEditor.mode.color : null;

  // Plan-click behavior depends on active tab + active mode.
  //   Cameras tab + 'placing' → drop a marker
  //   Zones tab + 'drawing'   → add a draft vertex
  //   Otherwise               → no-op
  const onPlaneClick =
    activeTab === 'cameras' && markerEditor.mode.kind === 'placing'
      ? (x: number, y: number) => markerEditor.placeAt(x, y)
      : activeTab === 'zones' && drawingZone
        ? (x: number, y: number) => zoneEditor.addDraftVertex(x, y)
        : undefined;

  function finishCurrentDraft() {
    zoneEditor.finishDrawing(
      t('floorPlan.zones.defaultName', { n: zoneEditor.zones.length + 1 })
    );
  }

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={handleBack}>
            <ArrowLeft className="h-4 w-4" />
            {t('common.back')}
          </Button>
          <div>
            <h1 className="text-lg font-semibold text-foreground">
              {plan.name}
            </h1>
            {plan.description && (
              <p className="text-xs text-muted-foreground">
                {plan.description}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Finish-drawing button — only when actively drawing a zone */}
          {drawingZone && draftPoints && draftPoints.length >= 3 && (
            <Button variant="outline" size="sm" onClick={finishCurrentDraft}>
              <CheckCheck className="h-4 w-4" />
              {t('floorPlan.zones.finish')}
            </Button>
          )}
          {dirty && (
            <span className="text-xs text-warning-foreground">
              {t('floorPlan.editor.unsaved')}
            </span>
          )}
          <Button onClick={handleSave} disabled={!dirty || saving}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            <Save className="h-4 w-4" />
            {t('common.save')}
          </Button>
        </div>
      </div>

      {/* Body: viewer + tabbed sidebar */}
      <div className="flex min-h-0 flex-1 overflow-hidden rounded-md border border-border">
        {/* min-w-0 REQUIRED so flex items can shrink below intrinsic width */}
        <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden bg-muted/10">
          <FloorPlanViewer
            plan={plan}
            onPlaneClick={onPlaneClick}
            onPlaneDoubleClick={
              drawingZone && draftPoints && draftPoints.length >= 3
                ? finishCurrentDraft
                : undefined
            }
          >
            {({ currentScale }) => (
              <>
                {/* Zones layer — interactive in zones tab, dimmed in cameras tab */}
                <div
                  style={{
                    opacity: activeTab === 'zones' ? 1 : 0.5,
                    transition: 'opacity 0.2s',
                  }}
                >
                  <ZonePolygonLayer
                    zones={zoneEditor.zones}
                    selectedZoneId={selectedZoneId}
                    draftPoints={draftPoints}
                    draftColor={draftColor}
                    editable={activeTab === 'zones' && canEditZones}
                    currentScale={currentScale}
                    imageWidthPx={plan.width_px}
                    imageHeightPx={plan.height_px}
                    onSelectZone={zoneEditor.selectZone}
                    onMoveVertex={zoneEditor.moveVertex}
                    onDeleteVertex={zoneEditor.deleteVertex}
                  />
                </div>
                {/* Markers layer — interactive in cameras tab, dimmed in zones tab */}
                <div
                  style={{
                    opacity: activeTab === 'cameras' ? 1 : 0.45,
                    transition: 'opacity 0.2s',
                  }}
                >
                  <MarkerLayer
                    markers={markerEditor.markers}
                    cameras={cameras || []}
                    selectedMarkerId={selectedMarkerId}
                    editable={activeTab === 'cameras' && canEditMarkers}
                    currentScale={currentScale}
                    imageWidthPx={plan.width_px}
                    imageHeightPx={plan.height_px}
                    onSelectMarker={markerEditor.selectMarker}
                    onMoveMarker={markerEditor.moveMarker}
                    onRemoveSelected={markerEditor.removeSelected}
                  />
                </div>
              </>
            )}
          </FloorPlanViewer>
        </div>

        {/* Tabbed sidebar */}
        <div className="flex w-72 flex-col border-s border-border bg-surface">
          <EditorSidebarTabs
            active={activeTab}
            onChange={setActiveTab}
            cameraCount={markerEditor.markers.length}
            zoneCount={zoneEditor.zones.length}
          />
          {activeTab === 'cameras' ? (
            <div className="min-h-0 flex-1 overflow-hidden">
              <CameraPaletteSidebar
                cameras={cameras || []}
                markers={markerEditor.markers}
                placingCameraId={placingCameraId}
                selectedMarkerId={selectedMarkerId}
                onPickForPlacement={markerEditor.pickForPlacement}
                onSelectMarker={markerEditor.selectMarker}
                onRemoveSelected={markerEditor.removeSelected}
                onCancel={markerEditor.cancel}
                onPatchMarker={markerEditor.patchMarker}
              />
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-hidden">
              <ZonePaletteSidebar
                zones={zoneEditor.zones}
                mode={zoneEditor.mode}
                onStartDrawing={zoneEditor.startDrawing}
                onCancelDrawing={zoneEditor.cancelDrawing}
                onSelectZone={zoneEditor.selectZone}
                onClearSelection={zoneEditor.clearSelection}
                onPatchSelected={zoneEditor.patchSelected}
                onRemoveSelected={zoneEditor.removeSelected}
                onAddRule={zoneEditor.addRule}
                onUpdateRule={zoneEditor.updateRule}
                onDeleteRule={zoneEditor.deleteRule}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
