import { useMemo } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  LayoutDashboard,
  Grid3x3,
  Map,
  Video,
  Shapes,
  Users,
  Building2,
  Bell,
  Clapperboard,
  BarChart3,
  FileText,
  UserCog,
  UserCircle2,
  ShieldCheck,
  Settings,
  Radar,
  Crosshair,
  LogOut,
} from 'lucide-react';
import { useAuth } from '@/shared/hooks/useAuth';
import { Logo } from '@/shared/components/Logo';
import { LanguageSwitcher } from '@/shared/components/LanguageSwitcher';
import { cn } from '@/shared/lib/cn';
import {
  CAMERA_READ,
  CAMERA_CALIBRATE,
  ZONE_READ,
  EMPLOYEE_READ,
  ALERT_READ,
  RECORDING_READ,
  ANALYTICS_READ,
  USER_READ,
  ROLE_READ,
  TENANT_READ,
  CAMERA_STREAM_VIEW,
  TRACK_READ,
} from '@/shared/lib/permissions';

interface NavItem {
  to: string;
  labelKey: string;
  icon: React.ComponentType<{ className?: string }>;
  permission?: string;
}

interface NavGroup {
  labelKey: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    labelKey: 'nav.monitoring',
    items: [
      { to: '/', labelKey: 'nav.overview', icon: LayoutDashboard },
      { to: '/live', labelKey: 'nav.liveWall', icon: Grid3x3, permission: CAMERA_STREAM_VIEW },
      { to: '/floor-plan', labelKey: 'nav.floorPlan', icon: Map, permission: TRACK_READ },
      { to: '/alerts', labelKey: 'nav.alerts', icon: Bell, permission: ALERT_READ },
      { to: '/persons', labelKey: 'nav.persons', icon: UserCircle2, permission: TRACK_READ },
      { to: '/bev', labelKey: 'nav.bev', icon: Radar, permission: TRACK_READ },
            { to: '/recordings', labelKey: 'nav.recordings', icon: Clapperboard, permission: RECORDING_READ },
      { to: '/analytics', labelKey: 'nav.analytics', icon: BarChart3, permission: ANALYTICS_READ },
      { to: '/reports/daily', labelKey: 'nav.reporting', icon: FileText, permission: ANALYTICS_READ },
    ],
  },
  {
    labelKey: 'nav.configuration',
    items: [
      { to: '/cameras', labelKey: 'nav.cameras', icon: Video, permission: CAMERA_READ },
      { to: '/calibration', labelKey: 'nav.calibration', icon: Crosshair, permission: CAMERA_CALIBRATE },
      { to: '/zones', labelKey: 'nav.zones', icon: Shapes, permission: ZONE_READ },
      { to: '/employees', labelKey: 'nav.employees', icon: Users, permission: EMPLOYEE_READ },
    ],
  },
  {
    labelKey: 'nav.administration',
    items: [
      { to: '/companies', labelKey: 'nav.companies', icon: Building2, permission: TENANT_READ },
      { to: '/users', labelKey: 'nav.users', icon: UserCog, permission: USER_READ },
      { to: '/roles', labelKey: 'nav.roles', icon: ShieldCheck, permission: ROLE_READ },
      { to: '/settings', labelKey: 'nav.settings', icon: Settings, permission: TENANT_READ },
    ],
  },
];

export function AppLayout() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, hasPermission, clear } = useAuth();

  // Depend on `user` (not just the stable `hasPermission` ref): permissions load
  // asynchronously after login, so without `user` here the memo never recomputes
  // and the sidebar shows only ungated items until a hard refresh.
  const visibleGroups = useMemo(
    () =>
      NAV_GROUPS.map((group) => ({
        ...group,
        items: group.items.filter((it) => !it.permission || hasPermission(it.permission)),
      })).filter((g) => g.items.length > 0),
    [hasPermission, user]
  );

  const handleLogout = () => {
    clear();
    navigate('/login', { replace: true });
  };

  const initials = (user?.full_name || user?.email || '?')
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <div className="flex min-h-screen bg-background">
      {/* Sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-e border-border bg-surface lg:flex">
        <div className="flex h-14 items-center gap-3 border-b border-border px-5">
          <Logo className="h-7 w-7" />
          <div className="flex flex-col leading-tight">
            <span className="text-sm font-semibold text-foreground">
              {t('app.name')}
            </span>
            <span className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
              {t('app.tagline')}
            </span>
          </div>
        </div>

        <nav className="scrollbar-thin flex-1 overflow-y-auto px-3 py-4">
          {visibleGroups.map((group) => (
            <div key={group.labelKey} className="mb-5">
              <div className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                {t(group.labelKey)}
              </div>
              <ul className="space-y-0.5">
                {group.items.map(({ to, labelKey, icon: Icon }) => (
                  <li key={to}>
                    <NavLink
                      to={to}
                      end={to === '/'}
                      className={({ isActive }) =>
                        cn(
                          'flex h-9 items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors',
                          isActive
                            ? 'bg-primary/10 text-primary'
                            : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                        )
                      }
                    >
                      <Icon className="h-4 w-4" />
                      <span>{t(labelKey)}</span>
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        {/* User pod */}
        <div className="border-t border-border p-3">
          <div className="flex items-center gap-3 rounded-md p-2">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/15 text-sm font-semibold text-primary">
              {initials}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-foreground">
                {user?.full_name}
              </div>
              <div className="truncate text-xs text-muted-foreground">
                {user?.email}
              </div>
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              aria-label={t('auth.signOut')}
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-end gap-2 border-b border-border bg-surface px-6">
          <LanguageSwitcher />
        </header>
        <main className="scrollbar-thin flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
