import { useTranslation } from 'react-i18next';
import { Edit2, Eye, FileText, MapPin, Trash2 } from 'lucide-react';
import { Card } from '@/shared/components/Card';
import { Badge } from '@/shared/components/Badge';
import type { FloorPlan } from '@/modules/floor-plan/types';
import type { Site } from '@/shared/types/api';

interface FloorPlanCardProps {
  plan: FloorPlan;
  site?: Site;
  canEdit: boolean;
  canDelete: boolean;
  onPreview: () => void;
  onEdit: () => void;
  onEditPlacement: () => void;
  onDelete: () => void;
}

/**
 * Compact card showing a floor plan's metadata. No image thumbnail in
 * Batch C (would need a server-side thumbnail variant — Batch F polish).
 */
export function FloorPlanCard({
  plan,
  site,
  canEdit,
  canDelete,
  onPreview,
  onEdit,
  onEditPlacement,
  onDelete,
}: FloorPlanCardProps) {
  const { t } = useTranslation();
  const sizeMB = (plan.original_size_bytes / 1024 / 1024).toFixed(2);
  const markerCount = plan.markers?.length || 0;

  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
          <FileText className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={onPreview}
            className="text-start text-base font-medium text-foreground hover:text-primary"
          >
            {plan.name}
          </button>
          {site && (
            <p className="text-xs text-muted-foreground">{site.name}</p>
          )}
          {plan.description && (
            <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
              {plan.description}
            </p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone="neutral">{plan.format.toUpperCase()}</Badge>
        <span className="text-muted-foreground">
          {plan.width_px}×{plan.height_px}px
        </span>
        <span className="text-muted-foreground">·</span>
        <span className="text-muted-foreground">{sizeMB} MB</span>
        {markerCount > 0 && (
          <>
            <span className="text-muted-foreground">·</span>
            <span className="flex items-center gap-1 text-muted-foreground">
              <MapPin className="h-3 w-3" />
              {t('floorPlan.card.markerCount', { count: markerCount })}
            </span>
          </>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-1 border-t border-border pt-3">
        <button
          type="button"
          onClick={onPreview}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <Eye className="h-3.5 w-3.5" />
          {t('floorPlan.card.preview')}
        </button>
        {canEdit && (
          <button
            type="button"
            onClick={onEditPlacement}
            className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <MapPin className="h-3.5 w-3.5" />
            {t('floorPlan.card.editPlacement')}
          </button>
        )}
        {canEdit && (
          <button
            type="button"
            onClick={onEdit}
            className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Edit2 className="h-3.5 w-3.5" />
            {t('common.edit')}
          </button>
        )}
        {canDelete && (
          <button
            type="button"
            onClick={onDelete}
            className="ms-auto flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-danger/10 hover:text-danger"
          >
            <Trash2 className="h-3.5 w-3.5" />
            {t('common.delete')}
          </button>
        )}
      </div>
    </Card>
  );
}
