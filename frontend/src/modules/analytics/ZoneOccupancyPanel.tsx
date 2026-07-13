import { useTranslation } from 'react-i18next';
import { MapPin } from 'lucide-react';
import { Badge } from '@/shared/components/Badge';
import { Card } from '@/shared/components/Card';
import { Spinner } from '@/shared/components/Spinner';
import { useZoneOccupancy } from '@/modules/analytics/api';

/**
 * Live per-zone headcount — total people present, split known (recognized
 * employee) vs unknown. Refreshes every 5s. A zone's people come from the
 * cameras whose floor-plan markers sit inside the zone polygon; "known" is
 * populated by the FaceTrack face-identity feed.
 */
export function ZoneOccupancyPanel() {
  const { t } = useTranslation();
  const { data, isLoading } = useZoneOccupancy(60);
  const zones = data?.zones ?? [];

  return (
    <div>
      <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold text-muted-foreground">
        <MapPin className="h-4 w-4" />
        {t('analytics.occupancy.heading')}
      </h2>

      {isLoading ? (
        <Spinner />
      ) : zones.length === 0 ? (
        <Card className="p-4 text-sm text-muted-foreground">
          {t('analytics.occupancy.empty')}
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
          {zones.map((z) => (
            <Card key={`${z.floor_plan_id}:${z.zone_id}`} className="p-4">
              <div className="flex items-center justify-between gap-2">
                <div className="truncate font-semibold">{z.zone_name}</div>
                {z.floor_plan_name && <Badge tone="neutral">{z.floor_plan_name}</Badge>}
              </div>

              <div className="mt-3 flex items-end gap-4">
                <div>
                  <div className="text-3xl font-bold tabular-nums leading-none">{z.total}</div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {t('analytics.occupancy.present')}
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge tone="success">{t('analytics.occupancy.known', { n: z.known })}</Badge>
                  <Badge tone="warning">{t('analytics.occupancy.unknown', { n: z.unknown })}</Badge>
                </div>
              </div>

              {z.known_people.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {z.known_people.slice(0, 12).map((p, i) => (
                    <span
                      key={`${p.emp_id}-${i}`}
                      className="rounded-full bg-success/10 px-2 py-0.5 text-xs text-success"
                    >
                      {p.name || p.emp_id}
                    </span>
                  ))}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
