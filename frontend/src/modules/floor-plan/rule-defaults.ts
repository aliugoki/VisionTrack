import {
  newId,
  type ZoneRule,
  type ZoneRuleKind,
} from '@/modules/floor-plan/types';

/**
 * Factory for new rules. We pick per-kind defaults that match the most
 * common operator intent for that kind:
 *
 *   occupancy_max: "Don't let more than N people in this zone" —
 *       starts with threshold=5, hold=30s (so brief spikes don't fire).
 *
 *   occupancy_min: "This zone should always have at least N watchers" —
 *       starts with threshold=1, hold=60s (avoid noise from brief gaps).
 *
 *   entry: "Tell me when anyone steps into this zone" —
 *       threshold=1, hold=0 (immediate edge fire).
 *
 *   dwell: Disabled in UI but defaults included defensively.
 *
 * Severity defaults to 'warning' — escalates to 'critical' when the
 * operator explicitly wants paging, demotes to 'info' for logs-only rules.
 *
 * Channels default to ['in_app'] only — email/whatsapp opt-in. This
 * matches what Batch C populated for fired alerts when channels weren't
 * yet user-controllable.
 */
export function newRule(kind: ZoneRuleKind): ZoneRule {
  const base: Omit<ZoneRule, 'kind' | 'threshold' | 'hold_time_s'> = {
    id: newId(),
    schedule: {
      mode: 'always',
      start_time: null,
      end_time: null,
      days: [],
    },
    severity: 'warning',
    channels: ['in_app'],
    enabled: true,
    label: null,
  };

  switch (kind) {
    case 'occupancy_max':
      return { ...base, kind, threshold: 5, hold_time_s: 30 };
    case 'occupancy_min':
      return { ...base, kind, threshold: 1, hold_time_s: 60 };
    case 'entry':
      return { ...base, kind, threshold: 1, hold_time_s: 0 };
    case 'dwell':
      return { ...base, kind, threshold: 1, hold_time_s: 60 };
  }
}

/**
 * Whether a rule is fully valid for save. Used by the edit modal to
 * gate the Apply button; mirrors the backend's pydantic validation
 * exactly so the round-trip is predictable.
 *
 * Returns an error key (matching i18n catalog) or null when valid.
 */
export function validateRule(r: ZoneRule): string | null {
  if (!Number.isFinite(r.threshold) || r.threshold < 0) {
    return 'floorPlan.zones.ruleEditor.errors.threshold';
  }
  if (!Number.isInteger(r.hold_time_s) || r.hold_time_s < 0) {
    return 'floorPlan.zones.ruleEditor.errors.holdTime';
  }
  if ((r.label?.length ?? 0) > 120) {
    return 'floorPlan.zones.ruleEditor.errors.labelTooLong';
  }
  if (r.schedule.mode === 'scheduled') {
    const hasDays = r.schedule.days.length > 0;
    const hasStart = !!r.schedule.start_time;
    const hasEnd = !!r.schedule.end_time;
    // Either time pair empty → require days. Either time set without
    // its partner → reject ("scheduled" needs both ends of a window).
    if (hasStart !== hasEnd) {
      return 'floorPlan.zones.ruleEditor.errors.timePair';
    }
    if (!hasDays && !hasStart) {
      // scheduled mode with neither days nor times = degenerate
      return 'floorPlan.zones.ruleEditor.errors.scheduleEmpty';
    }
  }
  if (r.channels.length === 0) {
    return 'floorPlan.zones.ruleEditor.errors.noChannel';
  }
  return null;
}

/**
 * Day labels for the day-picker. Index matches the schema convention
 * (0=Monday..6=Sunday) — also matches Python datetime.weekday().
 * Translation lookup keys, not literal strings.
 */
export const DAY_LABEL_KEYS: readonly string[] = [
  'floorPlan.zones.ruleEditor.days.mon',
  'floorPlan.zones.ruleEditor.days.tue',
  'floorPlan.zones.ruleEditor.days.wed',
  'floorPlan.zones.ruleEditor.days.thu',
  'floorPlan.zones.ruleEditor.days.fri',
  'floorPlan.zones.ruleEditor.days.sat',
  'floorPlan.zones.ruleEditor.days.sun',
];
