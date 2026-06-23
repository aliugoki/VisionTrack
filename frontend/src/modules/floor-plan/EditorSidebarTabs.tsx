import { useTranslation } from 'react-i18next';
import { Camera as CameraIcon, Shapes } from 'lucide-react';
import { cn } from '@/shared/lib/cn';

export type SidebarTab = 'cameras' | 'zones';

interface EditorSidebarTabsProps {
  active: SidebarTab;
  onChange: (tab: SidebarTab) => void;
  /** Counts shown as small badges on each tab. */
  cameraCount: number;
  zoneCount: number;
}

/**
 * Tab strip rendered above the floor plan editor's right sidebar.
 *
 * Lets operators flip between marker placement (Cameras tab) and zone
 * drawing (Zones tab). Each tab keeps its own sub-state via the parent
 * editor page — switching tabs doesn't lose unsaved changes in the
 * non-active section.
 */
export function EditorSidebarTabs({
  active,
  onChange,
  cameraCount,
  zoneCount,
}: EditorSidebarTabsProps) {
  const { t } = useTranslation();

  return (
    <div className="flex border-b border-border bg-surface">
      <TabButton
        active={active === 'cameras'}
        onClick={() => onChange('cameras')}
        icon={<CameraIcon className="h-3.5 w-3.5" />}
        label={t('floorPlan.editor.tabs.cameras')}
        count={cameraCount}
      />
      <TabButton
        active={active === 'zones'}
        onClick={() => onChange('zones')}
        icon={<Shapes className="h-3.5 w-3.5" />}
        label={t('floorPlan.editor.tabs.zones')}
        count={zoneCount}
      />
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
  count,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  count: number;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex flex-1 items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors',
        active
          ? 'border-b-2 border-primary text-primary'
          : 'border-b-2 border-transparent text-muted-foreground hover:text-foreground'
      )}
    >
      {icon}
      <span>{label}</span>
      {count > 0 && (
        <span
          className={cn(
            'rounded-full px-1.5 text-[10px]',
            active
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted text-muted-foreground'
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}
