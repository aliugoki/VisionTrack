import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Building2,
  ChevronRight,
  HardDrive,
  ShieldCheck,
  UserCog,
} from 'lucide-react';
import { Card } from '@/shared/components/Card';
import { useAuth } from '@/shared/hooks/useAuth';
import {
  RECORDING_READ,
  ROLE_READ,
  TENANT_READ,
  USER_READ,
} from '@/shared/lib/permissions';

/**
 * Settings hub — landing page for /settings.
 *
 * Each card links to a focused sub-page. Cards are gated by the
 * relevant permission so unprivileged users see only what they can
 * actually configure.
 */
export default function SettingsPage() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();

  const sections = [
    {
      key: 'organization',
      to: '/settings/organization',
      icon: Building2,
      permission: TENANT_READ,
    },
    {
      key: 'users',
      to: '/users',
      icon: UserCog,
      permission: USER_READ,
    },
    {
      key: 'roles',
      to: '/roles',
      icon: ShieldCheck,
      permission: ROLE_READ,
    },
    {
      key: 'storage',
      to: '/recordings',
      icon: HardDrive,
      permission: RECORDING_READ,
    },
  ].filter((s) => hasPermission(s.permission));

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">
          {t('settings.title')}
        </h1>
        <p className="text-sm text-muted-foreground">
          {t('settings.subtitle')}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {sections.map(({ key, to, icon: Icon }) => (
          <Link key={key} to={to}>
            <Card className="group flex items-center gap-3 p-4 transition hover:border-primary/40 hover:bg-muted/30">
              <div className="rounded-md bg-muted p-2">
                <Icon className="h-5 w-5 text-muted-foreground group-hover:text-foreground" />
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="truncate text-sm font-semibold text-foreground">
                  {t(`settings.sections.${key}.title`)}
                </h3>
                <p className="truncate text-xs text-muted-foreground">
                  {t(`settings.sections.${key}.body`)}
                </p>
              </div>
              <ChevronRight className="h-4 w-4 text-muted-foreground/60 group-hover:text-muted-foreground" />
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
