import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, X } from 'lucide-react';
import { cn } from '@/shared/lib/cn';
import type { NvencEstimate } from '@/modules/live-wall/useNvencEstimate';

interface NvencWarningProps {
  estimate: NvencEstimate;
  className?: string;
}

/**
 * Shown when the current tile assignment would stress the GPU's NVENC
 * session count. At `warn` level we tell the operator; at `exceeded`
 * level we make it clear transcodes will fail.
 *
 * The banner is dismissible per-session — once dismissed, it stays
 * hidden until the wall config changes pressure level (e.g. dismissed
 * at warn, then operator adds a 5th H.265 → reappears as exceeded).
 */
export function NvencWarning({ estimate, className }: NvencWarningProps) {
  const { t } = useTranslation();
  const [dismissedLevel, setDismissedLevel] = useState<string | null>(null);

  if (estimate.level === 'ok') return null;
  if (dismissedLevel === estimate.level) return null;

  const isError = estimate.level === 'exceeded';

  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-md border p-3 text-sm',
        isError
          ? 'border-danger/40 bg-danger/10 text-danger'
          : 'border-warning/40 bg-warning/10 text-warning-foreground',
        className
      )}
      role={isError ? 'alert' : 'status'}
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
      <div className="flex-1 space-y-1">
        <p className="font-medium">
          {isError
            ? t('liveWall.nvenc.exceededTitle')
            : t('liveWall.nvenc.warnTitle')}
        </p>
        <p className="text-xs opacity-90">
          {isError
            ? t('liveWall.nvenc.exceededBody', {
                count: estimate.h265Count,
                limit: estimate.limit,
              })
            : t('liveWall.nvenc.warnBody', {
                count: estimate.h265Count,
                limit: estimate.limit,
              })}
        </p>
      </div>
      <button
        type="button"
        onClick={() => setDismissedLevel(estimate.level)}
        className="rounded-full p-1 hover:bg-foreground/10"
        aria-label={t('common.dismiss')}
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
