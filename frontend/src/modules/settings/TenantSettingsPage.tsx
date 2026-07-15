import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Building2, Loader2, Save } from 'lucide-react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/shared/components/Button';
import { Card } from '@/shared/components/Card';
import { Input } from '@/shared/components/Input';
import { Select } from '@/shared/components/Select';
import { Spinner } from '@/shared/components/Spinner';
import { useAuth } from '@/shared/hooks/useAuth';
import { TENANT_UPDATE } from '@/shared/lib/permissions';
import { useTenant, useUpdateTenant } from '@/modules/settings/api';

/**
 * Common IANA timezones for Pakistan + Gulf markets, with a few
 * global anchors. Backend validates against the full IANA database
 * so any valid name works; this is just a curated UX shortlist.
 */
const TIMEZONE_OPTIONS = [
  'Asia/Karachi',
  'Asia/Dubai',
  'Asia/Riyadh',
  'Asia/Qatar',
  'Asia/Kuwait',
  'Asia/Muscat',
  'Asia/Bahrain',
  'Asia/Kolkata',
  'Asia/Singapore',
  'Asia/Bangkok',
  'Europe/London',
  'America/New_York',
  'UTC',
];

export default function TenantSettingsPage() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canEdit = hasPermission(TENANT_UPDATE);

  const { data: tenant, isLoading } = useTenant();
  const update = useUpdateTenant();

  // Form state — initialized from server data once loaded
  const [name, setName] = useState('');
  const [timezone, setTimezone] = useState('UTC');
  const [retentionDays, setRetentionDays] = useState(30);
  const [useDeepstream, setUseDeepstream] = useState(false);
  const [facetrackFeed, setFacetrackFeed] = useState(true);

  useEffect(() => {
    if (tenant) {
      setName(tenant.name);
      setTimezone(tenant.timezone);
      setRetentionDays(tenant.recording_retention_days);
      setUseDeepstream(tenant.use_deepstream);
      setFacetrackFeed(tenant.facetrack_feed_enabled);
    }
  }, [tenant]);

  if (isLoading || !tenant) {
    return (
      <div className="flex items-center justify-center p-12">
        <Spinner size={24} />
      </div>
    );
  }

  // Detect whether the form has unsaved changes
  const dirty =
    name !== tenant.name ||
    timezone !== tenant.timezone ||
    retentionDays !== tenant.recording_retention_days ||
    useDeepstream !== tenant.use_deepstream ||
    facetrackFeed !== tenant.facetrack_feed_enabled;

  const handleSave = async () => {
    try {
      await update.mutateAsync({
        name: name.trim() !== tenant.name ? name.trim() : undefined,
        timezone: timezone !== tenant.timezone ? timezone : undefined,
        recording_retention_days:
          retentionDays !== tenant.recording_retention_days
            ? retentionDays
            : undefined,
        use_deepstream:
          useDeepstream !== tenant.use_deepstream ? useDeepstream : undefined,
        facetrack_feed_enabled:
          facetrackFeed !== tenant.facetrack_feed_enabled
            ? facetrackFeed
            : undefined,
      });
      toast.success(t('settings.tenant.saveSuccess'));
    } catch (e: any) {
      toast.error(
        e?.response?.data?.detail || t('settings.tenant.saveError')
      );
    }
  };

  return (
    <div className="space-y-4">
      {/* Header with back link */}
      <div>
        <Link
          to="/settings"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-3 w-3" />
          {t('settings.title')}
        </Link>
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-foreground">
          <Building2 className="h-6 w-6" />
          {t('settings.sections.organization.title')}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t('settings.tenant.subtitle')}
        </p>
      </div>

      {/* Form card */}
      <Card className="p-4">
        <div className="space-y-4">
          {/* Org name */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-foreground">
              {t('settings.tenant.name')}
            </label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={!canEdit}
              maxLength={255}
            />
            <p className="text-xs text-muted-foreground">
              {t('settings.tenant.nameHelp')}
            </p>
          </div>

          {/* Subdomain (read-only) */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-foreground">
              {t('settings.tenant.subdomain')}
            </label>
            <Input value={tenant.subdomain} disabled readOnly />
            <p className="text-xs text-muted-foreground">
              {t('settings.tenant.subdomainHelp')}
            </p>
          </div>

          {/* Timezone */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-foreground">
              {t('settings.tenant.timezone')}
            </label>
            <Select
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
              disabled={!canEdit}
            >
              {TIMEZONE_OPTIONS.includes(timezone) ? null : (
                <option value={timezone}>{timezone}</option>
              )}
              {TIMEZONE_OPTIONS.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </Select>
            <p className="text-xs text-muted-foreground">
              {t('settings.tenant.timezoneHelp')}
            </p>
          </div>

          {/* Recording retention */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-foreground">
              {t('settings.tenant.retention')}
            </label>
            <div className="flex items-center gap-2">
              <Input
                type="number"
                min={1}
                max={3650}
                value={retentionDays}
                onChange={(e) =>
                  setRetentionDays(
                    Math.max(1, Math.min(3650, Number(e.target.value) || 1))
                  )
                }
                disabled={!canEdit}
                className="w-32"
              />
              <span className="text-sm text-muted-foreground">
                {t('settings.tenant.days')}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              {t('settings.tenant.retentionHelp')}
            </p>
          </div>

          {/* FaceTrack feed toggle */}
          <div className="space-y-1 border-t border-border pt-4">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={facetrackFeed}
                onChange={(e) => setFacetrackFeed(e.target.checked)}
                disabled={!canEdit}
                className="h-4 w-4 rounded border-input bg-surface text-primary focus:ring-2 focus:ring-ring"
              />
              <span className="text-sm font-medium text-foreground">
                {t('settings.tenant.facetrackFeed')}
              </span>
            </label>
            <p className="text-xs text-muted-foreground">
              {t('settings.tenant.facetrackFeedHelp')}
            </p>
          </div>

          {/* Plan + status (read-only metadata) */}
          <div className="grid grid-cols-2 gap-4 border-t border-border pt-4">
            <div>
              <p className="text-xs text-muted-foreground">
                {t('settings.tenant.plan')}
              </p>
              <p className="text-sm font-medium capitalize">{tenant.plan}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">
                {t('settings.tenant.status')}
              </p>
              <p className="text-sm font-medium">
                {tenant.is_active
                  ? t('settings.tenant.active')
                  : t('settings.tenant.inactive')}
              </p>
            </div>
          </div>

          {/* Save */}
          {canEdit && (
            <div className="flex justify-end gap-2 border-t border-border pt-4">
              <Button
                onClick={handleSave}
                disabled={!dirty || update.isPending}
              >
                {update.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Save className="h-3 w-3" />
                )}
                {t('settings.tenant.save')}
              </Button>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
