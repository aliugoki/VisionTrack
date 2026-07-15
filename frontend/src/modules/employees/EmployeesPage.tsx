import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Users, Search } from 'lucide-react';
import { Card } from '@/shared/components/Card';
import { Input } from '@/shared/components/Input';
import { Badge } from '@/shared/components/Badge';
import { Spinner } from '@/shared/components/Spinner';
import { useEmployees } from '@/modules/employees/api';

/**
 * Employee roster — synced from FaceTrack (the face-recognition system). Each
 * row's `emp_id` is the key the face-identity bridge uses, so "Recognized"
 * flags employees who have been seen on a VisionTrack camera.
 */
export default function EmployeesPage() {
  const { t } = useTranslation();
  const [search, setSearch] = useState('');
  const { data, isLoading } = useEmployees(search || undefined);
  const rows = data?.rows ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-foreground">
            <Users className="h-6 w-6" />
            {t('employees.title')}
          </h1>
          <p className="text-sm text-muted-foreground">{t('employees.subtitle')}</p>
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute start-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="ps-8"
            placeholder={t('employees.search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      <Card className="overflow-hidden p-0">
        {isLoading ? (
          <div className="p-8">
            <Spinner />
          </div>
        ) : rows.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            {t('employees.empty')}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 text-left font-semibold">{t('employees.name')}</th>
                  <th className="px-4 py-2.5 text-left font-semibold">{t('employees.empId')}</th>
                  <th className="px-4 py-2.5 text-left font-semibold">{t('employees.company')}</th>
                  <th className="px-4 py-2.5 text-left font-semibold">{t('employees.status')}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.id} className="border-t border-border/50">
                    <td className="px-4 py-2.5 font-medium">{e.name}</td>
                    <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">{e.emp_id}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{e.external_company_id || '—'}</td>
                    <td className="px-4 py-2.5">
                      {e.seen ? (
                        <Badge tone="success">{t('employees.recognized')}</Badge>
                      ) : (
                        <Badge tone="neutral">{t('employees.pending')}</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {rows.length > 0 && (
        <p className="text-xs text-muted-foreground">
          {t('employees.count', { n: data?.total ?? rows.length })}
        </p>
      )}
    </div>
  );
}
