import { useMemo } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ArrowLeft,
  CalendarClock,
  Camera as CameraIcon,
  Hash,
  Activity,
} from 'lucide-react';
import { Card } from '@/shared/components/Card';
import { Badge } from '@/shared/components/Badge';
import { Spinner } from '@/shared/components/Spinner';
import { usePerson } from '@/modules/persons/api';

/**
 * Single-person view — identity card + cross-camera timeline.
 *
 * The timeline lists every Track row attributed to this person, sorted
 * most-recent first. Each row links to the camera that produced it.
 */
export default function PersonDetailPage() {
  const { personId } = useParams<{ personId: string }>();
  const { t, i18n } = useTranslation();
  const { data: person, isLoading, isError } = usePerson(personId);

  const dateFmt = useMemo(
    () =>
      new Intl.DateTimeFormat(i18n.language === 'ar' ? 'ar-EG' : 'en-US', {
        dateStyle: 'medium',
        timeStyle: 'short',
      }),
    [i18n.language]
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-24">
        <Spinner />
      </div>
    );
  }

  if (isError || !person) {
    return (
      <div className="mx-auto max-w-3xl">
        <Card className="p-8 text-center">
          <h2 className="text-lg font-semibold text-foreground">
            {t('persons.detail.notFound')}
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            {t('persons.detail.notFoundHint')}
          </p>
          <Link
            to="/persons"
            className="mt-4 inline-flex items-center text-sm text-primary hover:underline"
          >
            <ArrowLeft className="h-4 w-4 me-1 rtl:rotate-180" />
            {t('persons.detail.backToList')}
          </Link>
        </Card>
      </div>
    );
  }

  // Duration of presence across all known sightings (rough — uses first/last)
  const durationMs =
    new Date(person.last_seen_at).getTime() -
    new Date(person.first_seen_at).getTime();
  const durationHrs = Math.max(0, Math.floor(durationMs / 1000 / 3600));

  // Unique cameras seen
  const uniqueCameras = new Set(
    person.timeline.map((t) => t.camera_id)
  ).size;

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <Link
          to="/persons"
          className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4 me-1 rtl:rotate-180" />
          {t('persons.detail.backToList')}
        </Link>
      </div>

      {/* Identity card */}
      <Card className="p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
              {t('persons.detail.identityHeading')}
            </div>
            <div className="mt-1 font-mono text-base text-foreground">
              {person.id}
            </div>
          </div>
          <Badge tone="primary">
            {t('persons.detail.appearanceBadge', {
              count: person.appearance_count,
            })}
          </Badge>
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-4">
          <Stat
            icon={<CalendarClock className="h-4 w-4" />}
            label={t('persons.detail.stats.firstSeen')}
            value={dateFmt.format(new Date(person.first_seen_at))}
          />
          <Stat
            icon={<CalendarClock className="h-4 w-4" />}
            label={t('persons.detail.stats.lastSeen')}
            value={dateFmt.format(new Date(person.last_seen_at))}
          />
          <Stat
            icon={<Activity className="h-4 w-4" />}
            label={t('persons.detail.stats.observed')}
            value={t('persons.detail.stats.hoursValue', { hours: durationHrs })}
          />
          <Stat
            icon={<CameraIcon className="h-4 w-4" />}
            label={t('persons.detail.stats.uniqueCameras')}
            value={String(uniqueCameras)}
          />
        </div>
      </Card>

      {/* Timeline */}
      <Card>
        <div className="border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-foreground">
            {t('persons.detail.timelineHeading')}
          </h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {t('persons.detail.timelineSubtitle', {
              count: person.timeline.length,
            })}
          </p>
        </div>

        {person.timeline.length === 0 ? (
          <div className="px-6 py-12 text-center text-sm text-muted-foreground">
            {t('persons.detail.timelineEmpty')}
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {person.timeline.map((entry) => {
              const start = new Date(entry.started_at);
              const end = entry.ended_at ? new Date(entry.ended_at) : null;
              const durationSec = end
                ? Math.max(0, Math.round((end.getTime() - start.getTime()) / 1000))
                : null;
              return (
                <li
                  key={entry.track_id}
                  className="flex items-center gap-4 px-6 py-3 text-sm transition-colors hover:bg-muted/30"
                >
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <CameraIcon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Link
                        to={`/cameras?focus=${entry.camera_id}`}
                        className="truncate font-medium text-foreground hover:text-primary"
                      >
                        {entry.camera_name ?? t('persons.detail.unknownCamera')}
                      </Link>
                      {!end && (
                        <Badge tone="success">
                          {t('persons.detail.activeBadge')}
                        </Badge>
                      )}
                    </div>
                    <div className="mt-0.5 flex items-center gap-3 text-xs text-muted-foreground">
                      <span>{dateFmt.format(start)}</span>
                      {durationSec !== null && (
                        <>
                          <span>·</span>
                          <span>
                            {t('persons.detail.durationLabel', {
                              seconds: durationSec,
                            })}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Hash className="h-3.5 w-3.5" />
                    <span>
                      {t('persons.detail.pointsLabel', {
                        count: entry.point_count,
                      })}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-muted-foreground">
        {icon}
        <span>{label}</span>
      </div>
      <div className="mt-1 text-sm font-medium text-foreground">{value}</div>
    </div>
  );
}
