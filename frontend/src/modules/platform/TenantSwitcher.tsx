import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Building2, ChevronDown, LogOut, Check } from 'lucide-react';
import { api } from '@/shared/api/client';
import { useAuth, type CurrentUser } from '@/shared/hooks/useAuth';

interface PlatformTenant {
  id: string;
  name: string;
  subdomain: string;
  external_company_id: string | null;
  is_active: boolean;
  employee_count: number;
  camera_count: number;
}

/**
 * Platform super-admin tenant switcher. In the platform session it lists every
 * company and lets you "enter" one (impersonate its admin, scoped token). While
 * inside a company it shows a banner to exit back to the platform.
 */
export function TenantSwitcher() {
  const { t } = useTranslation();
  const { user, actingTenant, beginActing, stopActing, setUser } = useAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const isPlatform = !!user?.is_platform_admin && !actingTenant;

  const { data } = useQuery({
    queryKey: ['platform', 'tenants'],
    enabled: isPlatform,
    queryFn: async () => {
      const res = await api.get<{ rows: PlatformTenant[] }>('/platform/tenants');
      return res.data.rows;
    },
  });

  async function enter(ten: PlatformTenant) {
    if (busy) return;
    setBusy(true);
    try {
      const { data: tok } = await api.post<{ access_token: string; refresh_token: string }>(
        `/platform/tenants/${ten.id}/enter`,
      );
      beginActing(tok.access_token, tok.refresh_token, { id: ten.id, name: ten.name });
      const me = await api.get<CurrentUser>('/users/me');
      setUser(me.data);
      qc.clear();
      setOpen(false);
      navigate('/');
      toast.success(t('platform.entered', { name: ten.name }));
    } catch {
      toast.error(t('common.error'));
      stopActing();
    } finally {
      setBusy(false);
    }
  }

  async function exit() {
    if (busy) return;
    setBusy(true);
    try {
      stopActing();
      const me = await api.get<CurrentUser>('/users/me');
      setUser(me.data);
      qc.clear();
      navigate('/');
    } catch {
      toast.error(t('common.error'));
    } finally {
      setBusy(false);
    }
  }

  // Currently inside a company (impersonating) — offer to exit.
  if (actingTenant) {
    return (
      <button
        type="button"
        onClick={exit}
        disabled={busy}
        className="flex w-full items-center justify-between gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning hover:bg-warning/20 disabled:opacity-50"
        title={t('platform.exit')}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <Building2 className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">{t('platform.viewing', { name: actingTenant.name })}</span>
        </span>
        <LogOut className="h-3.5 w-3.5 shrink-0" />
      </button>
    );
  }

  if (!isPlatform) return null;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
      >
        <span className="flex items-center gap-1.5">
          <Building2 className="h-3.5 w-3.5" />
          {t('platform.switchCompany')}
        </span>
        <ChevronDown className="h-3.5 w-3.5" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute bottom-full z-20 mb-1 max-h-72 w-full overflow-y-auto rounded-md border border-border bg-surface shadow-xl">
            {(data ?? []).map((ten) => (
              <button
                key={ten.id}
                type="button"
                onClick={() => enter(ten)}
                disabled={busy}
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm hover:bg-muted disabled:opacity-50"
              >
                <span className="min-w-0">
                  <span className="block truncate font-medium">{ten.name}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {t('platform.counts', { emp: ten.employee_count, cam: ten.camera_count })}
                  </span>
                </span>
                {user?.tenant_id === ten.id && <Check className="h-4 w-4 shrink-0 text-success" />}
              </button>
            ))}
            {(data ?? []).length === 0 && (
              <div className="px-3 py-2 text-xs text-muted-foreground">{t('platform.noTenants')}</div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
