import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/shared/lib/cn';
import type { PermissionCatalogItem } from '@/modules/roles/types';

interface PermissionMatrixProps {
  catalog: PermissionCatalogItem[];
  selected: string[];
  onChange: (next: string[]) => void;
  /** When true, all checkboxes are disabled (e.g. for read-only view). */
  disabled?: boolean;
}

/**
 * Two-level permission matrix.
 *
 *   - Top: master "Select all / clear all" toggle + total counter
 *   - Body: collapsible groups (Tenant, Users, Cameras, Zones, etc.)
 *     each with its own "group toggle" header that select-alls within
 *     that group
 *
 * Design choices:
 *   - Groups COLLAPSED by default → 56 perms in a flat list is overwhelming.
 *     User opens only the groups they care about.
 *   - Group header shows "5 / 7 selected" so you don't need to expand
 *     to see which groups have any permissions
 *   - Indeterminate state on the group header checkbox when only some
 *     permissions in the group are selected
 *
 * Keyed by permission `.key`; mutation is via callback so parent owns
 * the canonical state.
 */
export function PermissionMatrix({
  catalog,
  selected,
  onChange,
  disabled = false,
}: PermissionMatrixProps) {
  const { t } = useTranslation();

  // Bucket the catalog by group, preserving server-given order
  const groups = useMemo(() => {
    const m = new Map<string, PermissionCatalogItem[]>();
    for (const item of catalog) {
      const list = m.get(item.group) ?? [];
      list.push(item);
      m.set(item.group, list);
    }
    return Array.from(m.entries());
  }, [catalog]);

  // Set view for fast membership checks
  const selectedSet = useMemo(() => new Set(selected), [selected]);

  // Which groups are currently expanded — start with all collapsed.
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggleGroup = (g: string) => {
    setExpanded((s) => {
      const next = new Set(s);
      if (next.has(g)) {
        next.delete(g);
      } else {
        next.add(g);
      }
      return next;
    });
  };

  const togglePermission = (key: string) => {
    if (disabled) return;
    const next = new Set(selectedSet);
    if (next.has(key)) {
      next.delete(key);
    } else {
      next.add(key);
    }
    onChange(Array.from(next).sort());
  };

  const toggleGroupAll = (group: string, items: PermissionCatalogItem[]) => {
    if (disabled) return;
    const groupKeys = items.map((i) => i.key);
    const allSelected = groupKeys.every((k) => selectedSet.has(k));
    const next = new Set(selectedSet);
    if (allSelected) {
      for (const k of groupKeys) next.delete(k);
    } else {
      for (const k of groupKeys) next.add(k);
    }
    onChange(Array.from(next).sort());
  };

  const allSelected = catalog.length > 0 && selected.length === catalog.length;
  const noneSelected = selected.length === 0;

  const toggleAll = () => {
    if (disabled) return;
    if (allSelected) {
      onChange([]);
    } else {
      onChange(catalog.map((c) => c.key).sort());
    }
  };

  const expandAll = () => setExpanded(new Set(groups.map(([g]) => g)));
  const collapseAll = () => setExpanded(new Set());

  return (
    <div className="space-y-2">
      {/* Master toggle row */}
      <div className="flex items-center justify-between gap-2 rounded-md border border-border bg-muted/30 px-3 py-2">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={allSelected}
            ref={(el) => {
              if (el) {
                el.indeterminate = !allSelected && !noneSelected;
              }
            }}
            onChange={toggleAll}
            disabled={disabled}
            className="h-4 w-4 rounded border-border"
          />
          <span className="text-sm font-medium text-foreground">
            {t('roles.matrix.selectAll')}
          </span>
          <span className="text-xs text-muted-foreground">
            ({selected.length}/{catalog.length})
          </span>
        </label>
        <div className="flex gap-2 text-xs">
          <button
            type="button"
            onClick={expandAll}
            className="text-muted-foreground hover:text-foreground"
          >
            {t('roles.matrix.expandAll')}
          </button>
          <span className="text-muted-foreground/50">·</span>
          <button
            type="button"
            onClick={collapseAll}
            className="text-muted-foreground hover:text-foreground"
          >
            {t('roles.matrix.collapseAll')}
          </button>
        </div>
      </div>

      {/* Group accordions */}
      <div className="max-h-[55vh] space-y-1 overflow-y-auto pr-1">
        {groups.map(([group, items]) => {
          const inGroup = items.length;
          const selectedInGroup = items.filter((i) => selectedSet.has(i.key))
            .length;
          const allInGroupSelected = selectedInGroup === inGroup;
          const someInGroupSelected =
            selectedInGroup > 0 && selectedInGroup < inGroup;
          const isOpen = expanded.has(group);

          return (
            <div
              key={group}
              className="overflow-hidden rounded-md border border-border"
            >
              {/* Group header */}
              <div
                className={cn(
                  'flex items-center gap-2 px-3 py-2',
                  selectedInGroup > 0 ? 'bg-muted/30' : 'bg-card'
                )}
              >
                <button
                  type="button"
                  onClick={() => toggleGroup(group)}
                  className="text-muted-foreground hover:text-foreground"
                  aria-label={isOpen ? 'Collapse' : 'Expand'}
                >
                  {isOpen ? (
                    <ChevronDown className="h-4 w-4" />
                  ) : (
                    <ChevronRight className="h-4 w-4" />
                  )}
                </button>
                <input
                  type="checkbox"
                  checked={allInGroupSelected}
                  ref={(el) => {
                    if (el) el.indeterminate = someInGroupSelected;
                  }}
                  onChange={() => toggleGroupAll(group, items)}
                  disabled={disabled}
                  className="h-4 w-4 rounded border-border"
                />
                <span className="flex-1 text-sm font-medium text-foreground">
                  {group}
                </span>
                <span className="text-xs text-muted-foreground">
                  {selectedInGroup}/{inGroup}
                </span>
              </div>

              {/* Group body — only rendered when expanded */}
              {isOpen && (
                <div className="space-y-0.5 border-t border-border bg-background px-3 py-2">
                  {items.map((item) => (
                    <label
                      key={item.key}
                      className={cn(
                        'flex items-start gap-2 rounded px-1 py-1 hover:bg-muted/40',
                        disabled && 'cursor-not-allowed opacity-70'
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={selectedSet.has(item.key)}
                        onChange={() => togglePermission(item.key)}
                        disabled={disabled}
                        className="mt-0.5 h-4 w-4 flex-shrink-0 rounded border-border"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm text-foreground">{item.label}</p>
                        <p className="font-mono text-[10px] text-muted-foreground">
                          {item.key}
                        </p>
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
