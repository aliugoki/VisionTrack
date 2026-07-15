import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Shapes } from 'lucide-react';
import { Card } from '@/shared/components/Card';
import { Badge } from '@/shared/components/Badge';
import { Spinner } from '@/shared/components/Spinner';
import { useFloorPlans } from '@/modules/floor-plan/api';
import { useZoneOccupancy } from '@/modules/analytics/api';

/**
 * Zones overview — every zone across all floor plans, with its live occupancy.
 * Zones are polygons drawn on a floor plan (Floor Plans editor); this page lists
 * them and joins the live known/unknown headcount from the occupancy feed.
 */
export default function ZonesPage() {
  const { t } = useTranslation();
  const { data: plans, isLoading } = useFloorPlans();
  const { data: occ } = useZoneOccupancy(60);

  const occByZone = useMemo(() => {
    const m = new Map<string, { total: number; known: number; unknown: number }>();
    for (const z of occ?.zones ?? []) m.set(z.zone_id, { total: z.total, known: z.known, unknown: z.unknown });
    return m;
  }, [occ]);

  const zones = useMemo(() => {
    const out: {
      key: string;
      zone_id: string;
      name: string;
      color: string;
      plan: string;
      rules: number;
    }[] = [];
    for (const p of plans ?? []) {
      for (const z of p.zones ?? []) {
        out.push({
          key: `${p.id}:${z.id}`,
          zone_id: String(z.id),
          name: z.name || 'Zone',
          color: (z as { color?: string }).color || '#64748b',
          plan: p.name,
          rules: Array.isArray((z as { rules?: unknown[] }).rules) ? (z as { rules: unknown[] }).rules.length : 0,
        });
      }
    }
    return out.sort((a, b) => a.name.localeCompare(b.name));
  }, [plans]);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-foreground">
          <Shapes className="h-6 w-6" />
          {t('zonesPage.title')}
        </h1>
        <p className="text-sm text-muted-foreground">{t('zonesPage.subtitle')}</p>
      </div>

      <Card className="overflow-hidden p-0">
        {isLoading ? (
          <div className="p-8">
            <Spinner />
          </div>
        ) : zones.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            {t('zonesPage.empty')}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 text-left font-semibold">{t('zonesPage.zone')}</th>
                  <th className="px-4 py-2.5 text-left font-semibold">{t('zonesPage.floorPlan')}</th>
                  <th className="px-4 py-2.5 text-right font-semibold">{t('zonesPage.rules')}</th>
                  <th className="px-4 py-2.5 text-left font-semibold">{t('zonesPage.live')}</th>
                </tr>
              </thead>
              <tbody>
                {zones.map((z) => {
                  const o = occByZone.get(z.zone_id);
                  return (
                    <tr key={z.key} className="border-t border-border/50">
                      <td className="px-4 py-2.5">
                        <span className="flex items-center gap-2 font-medium">
                          <span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: z.color }} />
                          {z.name}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-muted-foreground">{z.plan}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-muted-foreground">{z.rules}</td>
                      <td className="px-4 py-2.5">
                        {o && o.total > 0 ? (
                          <span className="flex flex-wrap items-center gap-1.5">
                            <Badge tone="neutral">{t('zonesPage.present', { n: o.total })}</Badge>
                            <Badge tone="success">{t('analytics.occupancy.known', { n: o.known })}</Badge>
                            <Badge tone="warning">{t('analytics.occupancy.unknown', { n: o.unknown })}</Badge>
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">{t('zonesPage.emptyNow')}</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
