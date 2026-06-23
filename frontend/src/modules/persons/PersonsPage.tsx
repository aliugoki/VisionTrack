import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { UserSearch, ChevronRight, RefreshCw } from 'lucide-react';
import { Card } from '@/shared/components/Card';
import { Button } from '@/shared/components/Button';
import { Input } from '@/shared/components/Input';
import { Badge } from '@/shared/components/Badge';
import { Spinner } from '@/shared/components/Spinner';
import { usePersons } from '@/modules/persons/api';

const PAGE_SIZE = 50;

/**
 * Persons list — one row per cross-camera identity.
 *
 * Until the AI worker pipeline starts publishing embeddings and the
 * matcher creates rows, this page renders an empty state. That's
 * intentional — the data layer is in place so this UI lights up
 * automatically once embeddings flow.
 */
export default function PersonsPage() {
  const { t, i18n } = useTranslation();
  const [page, setPage] = useState(0);
  const [search, setSearch] = useState('');

  const { data: persons, isLoading, refetch, isFetching } = usePersons({
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  // Client-side filter on the ID prefix — the backend doesn't expose
  // person-name search yet (persons don't have names; the UI may add
  // labels in P3). For now the search is for finding a known ID.
  const filtered = useMemo(() => {
    if (!persons) return [];
    const q = search.trim().toLowerCase();
    if (!q) return persons;
    return persons.filter((p) => p.id.toLowerCase().includes(q));
  }, [persons, search]);

  const dateFmt = useMemo(
    () =>
      new Intl.DateTimeFormat(i18n.language === 'ar' ? 'ar-EG' : 'en-US', {
        dateStyle: 'medium',
        timeStyle: 'short',
      }),
    [i18n.language]
  );

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">
            {t('persons.title')}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t('persons.subtitle')}
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          <RefreshCw
            className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`}
          />
          <span className="ms-2">{t('common.refresh')}</span>
        </Button>
      </header>

      <Card className="p-4">
        <div className="flex items-center gap-3">
          <UserSearch className="h-4 w-4 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('persons.searchPlaceholder')}
            className="flex-1"
          />
        </div>
      </Card>

      <Card>
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <Spinner />
          </div>
        ) : !persons || persons.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-muted/40 text-xs uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-start font-semibold">
                    {t('persons.columns.id')}
                  </th>
                  <th className="px-4 py-3 text-start font-semibold">
                    {t('persons.columns.firstSeen')}
                  </th>
                  <th className="px-4 py-3 text-start font-semibold">
                    {t('persons.columns.lastSeen')}
                  </th>
                  <th className="px-4 py-3 text-start font-semibold">
                    {t('persons.columns.appearances')}
                  </th>
                  <th className="px-4 py-3" aria-hidden="true" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((person) => (
                  <tr
                    key={person.id}
                    className="border-t border-border transition-colors hover:bg-muted/30"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-foreground">
                      {person.id.slice(0, 8)}
                      <span className="text-muted-foreground">
                        …{person.id.slice(-4)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-foreground">
                      {dateFmt.format(new Date(person.first_seen_at))}
                    </td>
                    <td className="px-4 py-3 text-foreground">
                      {dateFmt.format(new Date(person.last_seen_at))}
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone="primary">
                        {person.appearance_count}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-end">
                      <Link
                        to={`/persons/${person.id}`}
                        className="inline-flex items-center text-primary hover:underline"
                      >
                        {t('common.view')}
                        <ChevronRight className="h-4 w-4 ms-1 rtl:rotate-180" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination footer */}
            <div className="flex items-center justify-between border-t border-border bg-muted/20 px-4 py-3 text-xs text-muted-foreground">
              <span>
                {t('persons.pagination.showing', {
                  count: filtered.length,
                  start: page * PAGE_SIZE + 1,
                  end: page * PAGE_SIZE + filtered.length,
                })}
              </span>
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page === 0}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                >
                  {t('common.previous')}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={!persons || persons.length < PAGE_SIZE}
                  onClick={() => setPage((p) => p + 1)}
                >
                  {t('common.next')}
                </Button>
              </div>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

function EmptyState() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
        <UserSearch className="h-7 w-7 text-primary" />
      </div>
      <h3 className="text-base font-semibold text-foreground">
        {t('persons.empty.title')}
      </h3>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">
        {t('persons.empty.description')}
      </p>
    </div>
  );
}
