import { useTranslation } from 'react-i18next';
import { Eye, EyeOff, Tag, TrendingUp } from 'lucide-react';
import { cn } from '@/shared/lib/cn';
import type { OverlayOptions } from '@/modules/tracks/TrackOverlay';

interface OverlayControlsProps {
  options: OverlayOptions;
  onChange: (next: OverlayOptions) => void;
  className?: string;
}

/**
 * Three small toggles overlaid on the bottom of the video player.
 * Each toggle is a pill button with an icon; active state is filled.
 */
export function OverlayControls({
  options,
  onChange,
  className,
}: OverlayControlsProps) {
  const { t } = useTranslation();

  return (
    <div
      className={cn(
        'absolute bottom-3 end-3 z-10 flex gap-1.5 rounded-full bg-background/70 px-1.5 py-1 backdrop-blur-sm',
        className
      )}
    >
      <ToggleButton
        icon={options.enabled ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
        label={t('tracks.overlay.toggleOverlay')}
        active={options.enabled}
        onClick={() => onChange({ ...options, enabled: !options.enabled })}
      />
      <ToggleButton
        icon={<Tag className="h-3.5 w-3.5" />}
        label={t('tracks.overlay.toggleLabels')}
        active={options.showLabels}
        disabled={!options.enabled}
        onClick={() =>
          onChange({ ...options, showLabels: !options.showLabels })
        }
      />
      <ToggleButton
        icon={<TrendingUp className="h-3.5 w-3.5" />}
        label={t('tracks.overlay.toggleTrails')}
        active={options.showTrails}
        disabled={!options.enabled}
        onClick={() =>
          onChange({ ...options, showTrails: !options.showTrails })
        }
      />
    </div>
  );
}

function ToggleButton({
  icon,
  label,
  active,
  disabled,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      aria-pressed={active}
      className={cn(
        'flex h-7 w-7 items-center justify-center rounded-full transition-colors',
        active && !disabled
          ? 'bg-primary text-primary-foreground'
          : 'text-muted-foreground hover:bg-muted hover:text-foreground',
        disabled && 'opacity-40 cursor-not-allowed'
      )}
    >
      {icon}
    </button>
  );
}
