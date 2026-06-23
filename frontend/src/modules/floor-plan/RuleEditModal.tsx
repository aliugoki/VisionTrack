import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Bell,
  Clock,
  Info,
  LogIn,
  TrendingDown,
  TrendingUp,
  Watch,
} from 'lucide-react';
import { Button } from '@/shared/components/Button';
import { Dialog } from '@/shared/components/Dialog';
import { Input } from '@/shared/components/Input';
import { cn } from '@/shared/lib/cn';
import type {
  ScheduleMode,
  ZoneRule,
  ZoneRuleChannel,
  ZoneRuleKind,
  ZoneRuleSeverity,
} from '@/modules/floor-plan/types';
import { DAY_LABEL_KEYS, validateRule } from '@/modules/floor-plan/rule-defaults';

interface RuleEditModalProps {
  open: boolean;
  /** Rule being edited. New rules are pre-populated by `newRule(kind)`. */
  rule: ZoneRule | null;
  /** Whether this is a freshly-created rule (changes button label). */
  isNew: boolean;
  onApply: (rule: ZoneRule) => void;
  onCancel: () => void;
}

/**
 * Modal form for editing one rule.
 *
 * The modal owns its own working copy of the rule (`draft` state). The
 * parent only sees the result via `onApply` — until then, edits don't
 * leak into the editor's dirty state. Cancel discards.
 *
 * Layout: vertical-stacked sections at md width (default), so even at
 * narrow viewports it remains usable. Schedule section expands only
 * when mode='scheduled'.
 */
export function RuleEditModal({
  open,
  rule,
  isNew,
  onApply,
  onCancel,
}: RuleEditModalProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<ZoneRule | null>(rule);

  // Sync draft with parent's rule when modal opens with new content.
  // We key the effect on rule?.id so reopening the modal for a different
  // rule resets the form.
  useEffect(() => {
    setDraft(rule);
  }, [rule?.id, open]);

  const errorKey = useMemo(() => (draft ? validateRule(draft) : null), [draft]);
  const valid = errorKey === null && draft !== null;

  if (!draft) return null;

  function patch(p: Partial<ZoneRule>) {
    setDraft((d) => (d ? { ...d, ...p } : d));
  }

  function patchSchedule(p: Partial<ZoneRule['schedule']>) {
    setDraft((d) => (d ? { ...d, schedule: { ...d.schedule, ...p } } : d));
  }

  function toggleDay(day: number) {
    setDraft((d) => {
      if (!d) return d;
      const has = d.schedule.days.includes(day);
      const next = has
        ? d.schedule.days.filter((x) => x !== day)
        : [...d.schedule.days, day].sort();
      return { ...d, schedule: { ...d.schedule, days: next } };
    });
  }

  function toggleChannel(ch: ZoneRuleChannel) {
    setDraft((d) => {
      if (!d) return d;
      const has = d.channels.includes(ch);
      const next = has
        ? d.channels.filter((x) => x !== ch)
        : [...d.channels, ch];
      return { ...d, channels: next };
    });
  }

  // For dwell rules: don't allow re-saving as enabled while Step 8 is
  // pending. If an old rule somehow has kind=dwell we let the user edit
  // it but the kind selector is locked.
  const isDwell = draft.kind === 'dwell';
  const scheduled = draft.schedule.mode === 'scheduled';

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => !o && onCancel()}
      title={isNew ? t('floorPlan.zones.ruleEditor.titleNew') : t('floorPlan.zones.ruleEditor.titleEdit')}
      size="md"
      footer={
        <div className="flex items-center justify-between gap-3">
          {/* Live validation hint on the left */}
          <div className="flex-1 min-w-0">
            {errorKey && (
              <p className="flex items-center gap-1.5 text-xs text-danger">
                <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
                <span className="truncate">{t(errorKey)}</span>
              </p>
            )}
          </div>
          <Button variant="ghost" onClick={onCancel}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={() => valid && draft && onApply(draft)}
            disabled={!valid}
          >
            {isNew
              ? t('floorPlan.zones.ruleEditor.add')
              : t('floorPlan.zones.ruleEditor.apply')}
          </Button>
        </div>
      }
    >
      <div className="space-y-5">
        {/* Kind */}
        <FieldGroup label={t('floorPlan.zones.ruleEditor.kind')}>
          <div className="grid grid-cols-2 gap-2">
            <KindCard
              active={draft.kind === 'occupancy_max'}
              icon={<TrendingUp className="h-4 w-4" />}
              title={t('floorPlan.zones.ruleEditor.kinds.occupancy_max')}
              hint={t('floorPlan.zones.ruleEditor.kindHints.occupancy_max')}
              onClick={() => patch({ kind: 'occupancy_max' })}
            />
            <KindCard
              active={draft.kind === 'occupancy_min'}
              icon={<TrendingDown className="h-4 w-4" />}
              title={t('floorPlan.zones.ruleEditor.kinds.occupancy_min')}
              hint={t('floorPlan.zones.ruleEditor.kindHints.occupancy_min')}
              onClick={() => patch({ kind: 'occupancy_min' })}
            />
            <KindCard
              active={draft.kind === 'entry'}
              icon={<LogIn className="h-4 w-4" />}
              title={t('floorPlan.zones.ruleEditor.kinds.entry')}
              hint={t('floorPlan.zones.ruleEditor.kindHints.entry')}
              onClick={() => patch({ kind: 'entry' })}
            />
            <KindCard
              active={draft.kind === 'dwell'}
              disabled={!isDwell}
              icon={<Watch className="h-4 w-4" />}
              title={t('floorPlan.zones.ruleEditor.kinds.dwell')}
              hint={t('floorPlan.zones.ruleEditor.kindHints.dwell')}
              onClick={() => {
                // We don't ALLOW selecting dwell — only viewable if rule
                // is already dwell. This branch is a no-op for new rules.
              }}
            />
          </div>
        </FieldGroup>

        {/* Threshold + Hold time */}
        <div className="grid grid-cols-2 gap-3">
          <FieldGroup label={t('floorPlan.zones.ruleEditor.threshold')}>
            <Input
              type="number"
              min={0}
              step={draft.kind === 'entry' ? 1 : 1}
              value={draft.threshold}
              onChange={(e) =>
                patch({ threshold: Number(e.target.value) || 0 })
              }
            />
            <Hint>
              {draft.kind === 'occupancy_max' &&
                t('floorPlan.zones.ruleEditor.thresholdHints.max')}
              {draft.kind === 'occupancy_min' &&
                t('floorPlan.zones.ruleEditor.thresholdHints.min')}
              {draft.kind === 'entry' &&
                t('floorPlan.zones.ruleEditor.thresholdHints.entry')}
              {draft.kind === 'dwell' &&
                t('floorPlan.zones.ruleEditor.thresholdHints.dwell')}
            </Hint>
          </FieldGroup>

          <FieldGroup label={t('floorPlan.zones.ruleEditor.holdTime')}>
            <Input
              type="number"
              min={0}
              step={1}
              value={draft.hold_time_s}
              onChange={(e) =>
                patch({ hold_time_s: parseInt(e.target.value || '0', 10) })
              }
              disabled={draft.kind === 'entry'}
            />
            <Hint>
              {draft.kind === 'entry'
                ? t('floorPlan.zones.ruleEditor.holdHints.entry')
                : t('floorPlan.zones.ruleEditor.holdHints.occupancy')}
            </Hint>
          </FieldGroup>
        </div>

        {/* Label */}
        <FieldGroup
          label={t('floorPlan.zones.ruleEditor.label')}
          optional
        >
          <Input
            type="text"
            maxLength={120}
            value={draft.label ?? ''}
            onChange={(e) =>
              patch({ label: e.target.value || null })
            }
            placeholder={t('floorPlan.zones.ruleEditor.labelPlaceholder')}
          />
        </FieldGroup>

        {/* Severity */}
        <FieldGroup label={t('floorPlan.zones.ruleEditor.severity')}>
          <div className="grid grid-cols-3 gap-2">
            <SeverityChip
              active={draft.severity === 'info'}
              variant="info"
              icon={<Info className="h-3.5 w-3.5" />}
              label={t('floorPlan.zones.ruleEditor.severities.info')}
              onClick={() => patch({ severity: 'info' })}
            />
            <SeverityChip
              active={draft.severity === 'warning'}
              variant="warning"
              icon={<AlertTriangle className="h-3.5 w-3.5" />}
              label={t('floorPlan.zones.ruleEditor.severities.warning')}
              onClick={() => patch({ severity: 'warning' })}
            />
            <SeverityChip
              active={draft.severity === 'critical'}
              variant="critical"
              icon={<Bell className="h-3.5 w-3.5" />}
              label={t('floorPlan.zones.ruleEditor.severities.critical')}
              onClick={() => patch({ severity: 'critical' })}
            />
          </div>
        </FieldGroup>

        {/* Channels */}
        <FieldGroup label={t('floorPlan.zones.ruleEditor.channels')}>
          <div className="space-y-1.5">
            <ChannelRow
              checked={draft.channels.includes('in_app')}
              label={t('floorPlan.zones.ruleEditor.channelLabels.in_app')}
              hint={t('floorPlan.zones.ruleEditor.channelHints.in_app')}
              onChange={() => toggleChannel('in_app')}
            />
            <ChannelRow
              checked={draft.channels.includes('email')}
              label={t('floorPlan.zones.ruleEditor.channelLabels.email')}
              hint={t('floorPlan.zones.ruleEditor.channelHints.email')}
              onChange={() => toggleChannel('email')}
            />
            <ChannelRow
              checked={draft.channels.includes('whatsapp')}
              label={t('floorPlan.zones.ruleEditor.channelLabels.whatsapp')}
              hint={t('floorPlan.zones.ruleEditor.channelHints.whatsapp')}
              onChange={() => toggleChannel('whatsapp')}
            />
          </div>
        </FieldGroup>

        {/* Schedule */}
        <FieldGroup label={t('floorPlan.zones.ruleEditor.schedule')}>
          <div className="space-y-2">
            <div className="flex gap-2">
              <ScheduleModeChip
                active={draft.schedule.mode === 'always'}
                label={t('floorPlan.zones.ruleEditor.scheduleModes.always')}
                onClick={() => patchSchedule({ mode: 'always' })}
              />
              <ScheduleModeChip
                active={draft.schedule.mode === 'scheduled'}
                label={t('floorPlan.zones.ruleEditor.scheduleModes.scheduled')}
                onClick={() => patchSchedule({ mode: 'scheduled' })}
              />
            </div>

            {scheduled && (
              <div className="space-y-3 rounded-md border border-border bg-muted/30 p-3">
                {/* Days */}
                <div>
                  <p className="mb-1.5 text-xs text-muted-foreground">
                    {t('floorPlan.zones.ruleEditor.days.label')}
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {DAY_LABEL_KEYS.map((labelKey, idx) => {
                      const selected = draft.schedule.days.includes(idx);
                      return (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => toggleDay(idx)}
                          className={cn(
                            'h-7 w-9 rounded-md border text-xs font-medium transition-colors',
                            selected
                              ? 'border-primary bg-primary text-primary-foreground'
                              : 'border-border bg-background text-muted-foreground hover:bg-muted'
                          )}
                        >
                          {t(labelKey)}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Time window */}
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="mb-1 block text-xs text-muted-foreground">
                      {t('floorPlan.zones.ruleEditor.startTime')}
                    </label>
                    <Input
                      type="time"
                      value={draft.schedule.start_time ?? ''}
                      onChange={(e) =>
                        patchSchedule({
                          start_time: e.target.value || null,
                        })
                      }
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs text-muted-foreground">
                      {t('floorPlan.zones.ruleEditor.endTime')}
                    </label>
                    <Input
                      type="time"
                      value={draft.schedule.end_time ?? ''}
                      onChange={(e) =>
                        patchSchedule({
                          end_time: e.target.value || null,
                        })
                      }
                    />
                  </div>
                </div>
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  {t('floorPlan.zones.ruleEditor.crossMidnightHint')}
                </p>
              </div>
            )}
          </div>
        </FieldGroup>

        {/* Enabled */}
        <FieldGroup label={t('floorPlan.zones.ruleEditor.enabled')}>
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(e) => patch({ enabled: e.target.checked })}
              className="h-4 w-4 rounded border-border accent-primary"
            />
            <span>
              {draft.enabled
                ? t('floorPlan.zones.ruleEditor.enabledOn')
                : t('floorPlan.zones.ruleEditor.enabledOff')}
            </span>
          </label>
        </FieldGroup>
      </div>
    </Dialog>
  );
}

// -- Subcomponents ------------------------------------------------------------

function FieldGroup({
  label,
  optional,
  children,
}: {
  label: string;
  optional?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium text-foreground">
        {label}
        {optional && (
          <span className="ms-1.5 text-muted-foreground">(optional)</span>
        )}
      </p>
      {children}
    </div>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 text-xs text-muted-foreground">{children}</p>;
}

function KindCard({
  active,
  disabled,
  icon,
  title,
  hint,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  icon: React.ReactNode;
  title: string;
  hint: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      className={cn(
        'flex flex-col items-start gap-1 rounded-md border p-2.5 text-start text-xs transition-colors',
        active
          ? 'border-primary bg-primary/5'
          : 'border-border bg-background hover:bg-muted',
        disabled && 'cursor-not-allowed opacity-50 hover:bg-background'
      )}
    >
      <div className="flex items-center gap-1.5">
        {icon}
        <span className="font-medium text-foreground">{title}</span>
      </div>
      <span className="text-[11px] leading-snug text-muted-foreground">
        {hint}
      </span>
    </button>
  );
}

function SeverityChip({
  active,
  variant,
  icon,
  label,
  onClick,
}: {
  active: boolean;
  variant: 'info' | 'warning' | 'critical';
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  const colors: Record<typeof variant, string> = {
    info: active
      ? 'border-sky-500 bg-sky-500/15 text-sky-700 dark:text-sky-300'
      : 'border-border bg-background text-muted-foreground hover:bg-muted',
    warning: active
      ? 'border-amber-500 bg-amber-500/15 text-amber-700 dark:text-amber-300'
      : 'border-border bg-background text-muted-foreground hover:bg-muted',
    critical: active
      ? 'border-red-500 bg-red-500/15 text-red-700 dark:text-red-300'
      : 'border-border bg-background text-muted-foreground hover:bg-muted',
  };
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex items-center justify-center gap-1.5 rounded-md border px-2 py-1.5 text-xs font-medium transition-colors',
        colors[variant]
      )}
    >
      {icon}
      {label}
    </button>
  );
}

function ChannelRow({
  checked,
  label,
  hint,
  onChange,
}: {
  checked: boolean;
  label: string;
  hint: string;
  onChange: () => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-2 rounded-md p-1.5 hover:bg-muted/40">
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        className="mt-0.5 h-4 w-4 rounded border-border accent-primary"
      />
      <div className="flex-1">
        <p className="text-sm text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </div>
    </label>
  );
}

function ScheduleModeChip({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex-1 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors',
        active
          ? 'border-primary bg-primary text-primary-foreground'
          : 'border-border bg-background text-muted-foreground hover:bg-muted'
      )}
    >
      {label}
    </button>
  );
}
