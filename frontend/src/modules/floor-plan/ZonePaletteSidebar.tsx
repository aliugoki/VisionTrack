import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Bell,
  Info,
  LogIn,
  Pencil,
  Plus,
  Trash2,
  TrendingDown,
  TrendingUp,
  Watch,
  X,
} from 'lucide-react';
import { cn } from '@/shared/lib/cn';
import {
  ZONE_COLORS,
  type Zone,
  type ZoneRule,
  type ZoneRuleKind,
} from '@/modules/floor-plan/types';
import type { ZoneEditMode } from '@/modules/floor-plan/useZoneEditing';
import { RuleEditModal } from '@/modules/floor-plan/RuleEditModal';
import { newRule } from '@/modules/floor-plan/rule-defaults';

interface ZonePaletteSidebarProps {
  zones: Zone[];
  mode: ZoneEditMode;
  onStartDrawing: (color: string) => void;
  onCancelDrawing: () => void;
  onSelectZone: (zoneId: string) => void;
  onClearSelection: () => void;
  onPatchSelected: (patch: Partial<Pick<Zone, 'name' | 'color'>>) => void;
  onRemoveSelected: () => void;
  // Rule callbacks (Batch D)
  onAddRule: (zoneId: string, rule: ZoneRule) => void;
  onUpdateRule: (zoneId: string, ruleId: string, next: ZoneRule) => void;
  onDeleteRule: (zoneId: string, ruleId: string) => void;
}

/**
 * Right-side sidebar content for zone editing mode.
 *
 * Three sections, top to bottom:
 *   1. Header — "+ New zone" button when idle, "Drawing..." status when drawing
 *   2. Zone list — all existing zones, click to select
 *   3. Selected zone editor — name input, color picker (when a zone is selected)
 *
 * Rules editing (per-zone alert rules) is intentionally NOT here — that's
 * Batch D. When a zone is selected we show a placeholder explaining where
 * rules will live.
 */
export function ZonePaletteSidebar({
  zones,
  mode,
  onStartDrawing,
  onCancelDrawing,
  onSelectZone,
  onClearSelection,
  onPatchSelected,
  onRemoveSelected,
  onAddRule,
  onUpdateRule,
  onDeleteRule,
}: ZonePaletteSidebarProps) {
  const { t } = useTranslation();

  // Modal state. `editing` is null when closed; `{rule, isNew}` when open.
  // We keep the working rule object in modal state (the modal further
  // copies it into its own draft state — see RuleEditModal). When the
  // modal applies, we dispatch to addRule/updateRule.
  const [editing, setEditing] = useState<{
    rule: ZoneRule;
    zoneId: string;
    isNew: boolean;
  } | null>(null);

  function openNewRule(zoneId: string, kind: ZoneRuleKind = 'occupancy_max') {
    setEditing({ rule: newRule(kind), zoneId, isNew: true });
  }
  function openEditRule(zoneId: string, rule: ZoneRule) {
    setEditing({ rule, zoneId, isNew: false });
  }
  function applyFromModal(next: ZoneRule) {
    if (!editing) return;
    if (editing.isNew) {
      onAddRule(editing.zoneId, next);
    } else {
      onUpdateRule(editing.zoneId, next.id, next);
    }
    setEditing(null);
  }

  const selectedZone = useMemo(
    () =>
      mode.kind === 'selected'
        ? zones.find((z) => z.id === mode.zoneId) || null
        : null,
    [mode, zones]
  );

  const drawing = mode.kind === 'drawing';
  const draftCount = drawing ? mode.draftPoints.length : 0;

  return (
    <aside className="flex h-full w-72 flex-col overflow-hidden border-s border-border bg-surface">
      {/* Scrollable single column */}
      <div className="flex-1 space-y-4 overflow-y-auto p-3">
        {/* --- Header / action button --- */}
        {!drawing && (
          <button
            type="button"
            onClick={() => onStartDrawing(ZONE_COLORS[0])}
            className="flex w-full items-center justify-center gap-2 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            {t('floorPlan.zones.newZone')}
          </button>
        )}

        {drawing && (
          <div className="rounded-md border border-primary bg-primary/10 p-3 text-sm">
            <p className="font-medium text-foreground">
              {t('floorPlan.zones.drawing.title')}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              {draftCount < 3
                ? t('floorPlan.zones.drawing.needMore', {
                    count: 3 - draftCount,
                  })
                : t('floorPlan.zones.drawing.ready')}
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              {t('floorPlan.zones.drawing.hint')}
            </p>
            <button
              type="button"
              onClick={onCancelDrawing}
              className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 text-xs text-foreground hover:bg-muted"
            >
              <X className="h-3 w-3" />
              {t('floorPlan.zones.drawing.cancel')}
            </button>
          </div>
        )}

        {/* --- Zone list --- */}
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {t('floorPlan.zones.listHeading', { count: zones.length })}
          </h3>
          {zones.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              {t('floorPlan.zones.empty')}
            </p>
          ) : (
            <ul className="space-y-0.5">
              {zones.map((z) => {
                const isSel = selectedZone?.id === z.id;
                return (
                  <li
                    key={z.id}
                    className={cn(
                      'flex items-center gap-2 rounded-md px-2 py-1.5 text-sm',
                      isSel
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-muted'
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => onSelectZone(z.id)}
                      className="flex min-w-0 flex-1 items-center gap-2 text-start"
                    >
                      <span
                        className="h-3 w-3 flex-shrink-0 rounded-sm border border-black/20"
                        style={{ background: z.color }}
                      />
                      <span className="truncate">{z.name}</span>
                      <span
                        className={cn(
                          'flex-shrink-0 text-xs',
                          isSel ? 'opacity-80' : 'text-muted-foreground'
                        )}
                      >
                        {z.polygon.length}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* --- Selected zone editor --- */}
        {selectedZone && (
          <div className="border-t border-border pt-3">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {t('floorPlan.zones.editing')}
              </h3>
              <button
                type="button"
                onClick={onClearSelection}
                className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                aria-label={t('common.close')}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Name input */}
            <div className="mb-3">
              <label className="mb-1 block text-xs text-muted-foreground">
                {t('floorPlan.zones.fields.name')}
              </label>
              <input
                type="text"
                value={selectedZone.name}
                onChange={(e) => onPatchSelected({ name: e.target.value })}
                maxLength={120}
                className="w-full rounded-md border border-border bg-background px-2 py-1 text-sm text-foreground focus:border-primary focus:outline-none"
              />
            </div>

            {/* Color picker */}
            <div className="mb-3">
              <label className="mb-1 block text-xs text-muted-foreground">
                {t('floorPlan.zones.fields.color')}
              </label>
              <div className="grid grid-cols-8 gap-1">
                {ZONE_COLORS.map((c) => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => onPatchSelected({ color: c })}
                    className={cn(
                      'h-6 w-6 rounded-sm border-2 transition-transform hover:scale-110',
                      selectedZone.color === c
                        ? 'border-foreground'
                        : 'border-transparent'
                    )}
                    style={{ background: c }}
                    aria-label={c}
                    title={c}
                  />
                ))}
              </div>
            </div>

            {/* Rules section */}
            <div className="mb-3">
              <div className="mb-1.5 flex items-center justify-between">
                <p className="text-xs font-medium text-foreground">
                  {t('floorPlan.zones.rules.heading')}
                  <span className="ms-1.5 rounded bg-muted px-1 text-[10px] text-muted-foreground">
                    {selectedZone.rules.length}
                  </span>
                </p>
                <button
                  type="button"
                  onClick={() => openNewRule(selectedZone.id)}
                  className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-primary hover:bg-primary/10"
                >
                  <Plus className="h-3 w-3" />
                  {t('floorPlan.zones.rules.add')}
                </button>
              </div>
              {selectedZone.rules.length === 0 ? (
                <p className="rounded-md border border-dashed border-border p-2 text-xs text-muted-foreground">
                  {t('floorPlan.zones.rules.empty')}
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {selectedZone.rules.map((r) => (
                    <RuleCard
                      key={r.id}
                      rule={r}
                      onEdit={() => openEditRule(selectedZone.id, r)}
                      onDelete={() => {
                        if (window.confirm(t('floorPlan.zones.rules.deleteConfirm'))) {
                          onDeleteRule(selectedZone.id, r.id);
                        }
                      }}
                    />
                  ))}
                </ul>
              )}
            </div>

            {/* Remove zone */}
            <button
              type="button"
              onClick={onRemoveSelected}
              className="flex w-full items-center justify-center gap-1.5 rounded-md border border-danger/40 px-2 py-1 text-xs text-danger hover:bg-danger/10"
            >
              <Trash2 className="h-3 w-3" />
              {t('floorPlan.zones.deleteZone')}
            </button>
          </div>
        )}
      </div>

      {/* Rule edit modal — rendered at sidebar root so it covers the full
          screen via portal, not constrained to the sidebar width. */}
      <RuleEditModal
        open={editing !== null}
        rule={editing?.rule ?? null}
        isNew={editing?.isNew ?? false}
        onApply={applyFromModal}
        onCancel={() => setEditing(null)}
      />
    </aside>
  );
}

// -- RuleCard ----------------------------------------------------------------
// Compact rule summary shown in the sidebar list. Click anywhere → edit.
// Pencil/trash icons appear on hover.

const KIND_ICONS: Record<ZoneRule['kind'], React.ComponentType<{ className?: string }>> = {
  occupancy_max: TrendingUp,
  occupancy_min: TrendingDown,
  entry: LogIn,
  dwell: Watch,
};

const SEVERITY_DOT: Record<ZoneRule['severity'], string> = {
  info: 'bg-sky-500',
  warning: 'bg-amber-500',
  critical: 'bg-red-500',
};

function RuleCard({
  rule,
  onEdit,
  onDelete,
}: {
  rule: ZoneRule;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const Icon = KIND_ICONS[rule.kind];

  // Build a one-line summary: "kind: threshold (hold)" — terse, scannable.
  const summary = (() => {
    if (rule.kind === 'entry') {
      return t('floorPlan.zones.rules.summary.entry', { n: rule.threshold });
    }
    if (rule.kind === 'occupancy_max') {
      return t('floorPlan.zones.rules.summary.occupancy_max', {
        n: rule.threshold,
        s: rule.hold_time_s,
      });
    }
    if (rule.kind === 'occupancy_min') {
      return t('floorPlan.zones.rules.summary.occupancy_min', {
        n: rule.threshold,
        s: rule.hold_time_s,
      });
    }
    return t('floorPlan.zones.rules.summary.dwell', { s: rule.hold_time_s });
  })();

  return (
    <li
      className={cn(
        'group flex items-start gap-2 rounded-md border border-border bg-background p-2 hover:border-primary',
        !rule.enabled && 'opacity-60'
      )}
    >
      {/* Severity dot + kind icon */}
      <div className="flex flex-col items-center pt-0.5">
        <span className={cn('h-1.5 w-1.5 rounded-full', SEVERITY_DOT[rule.severity])} />
        <Icon className="mt-1 h-3.5 w-3.5 text-muted-foreground" />
      </div>

      {/* Click-to-edit central area */}
      <button
        type="button"
        onClick={onEdit}
        className="min-w-0 flex-1 text-start"
      >
        {rule.label && (
          <p className="truncate text-xs font-medium text-foreground">
            {rule.label}
          </p>
        )}
        <p className="text-xs text-muted-foreground">{summary}</p>
        {!rule.enabled && (
          <p className="mt-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            {t('floorPlan.zones.rules.disabled')}
          </p>
        )}
      </button>

      {/* Hover actions */}
      <div className="flex flex-col gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
        <button
          type="button"
          onClick={onEdit}
          className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          title={t('common.edit')}
        >
          <Pencil className="h-3 w-3" />
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="rounded p-0.5 text-muted-foreground hover:bg-danger/10 hover:text-danger"
          title={t('common.delete')}
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>
    </li>
  );
}
