import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Building2, LogIn, Pause, Play, Trash2, Settings2 } from 'lucide-react';
import { Card } from '@/shared/components/Card';
import { Button } from '@/shared/components/Button';
import { Input } from '@/shared/components/Input';
import { Badge } from '@/shared/components/Badge';
import { Spinner } from '@/shared/components/Spinner';
import { Dialog } from '@/shared/components/Dialog';
import { useAuth } from '@/shared/hooks/useAuth';
import {
  usePlatformTenants,
  useUpdateTenant,
  useDeleteTenant,
  useEnterTenant,
  type PlatformTenant,
} from '@/modules/platform/api';

/**
 * Platform tenant management (platform admins only) — every company's isolated
 * tenant with lifecycle actions: enter, suspend/activate, edit settings, delete
 * (suspend first). Reflects the FaceTrack company roster provisioned in Phase 1.
 */
export default function PlatformTenantsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { data, isLoading } = usePlatformTenants();
  const rows = data?.rows ?? [];
  const update = useUpdateTenant();
  const del = useDeleteTenant();
  const enterTenant = useEnterTenant();
  const [editing, setEditing] = useState<PlatformTenant | null>(null);
  const [deleting, setDeleting] = useState<PlatformTenant | null>(null);

  async function toggleActive(ten: PlatformTenant) {
    try {
      await update.mutateAsync({ id: ten.id, is_active: !ten.is_active });
      toast.success(t(ten.is_active ? 'platform.suspended' : 'platform.activated', { name: ten.name }));
    } catch {
      toast.error(t('common.error'));
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-foreground">
          <Building2 className="h-6 w-6" />
          {t('platform.title')}
        </h1>
        <p className="text-sm text-muted-foreground">{t('platform.subtitle')}</p>
      </div>

      <Card className="overflow-hidden p-0">
        {isLoading ? (
          <div className="p-8"><Spinner /></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 text-left font-semibold">{t('platform.company')}</th>
                  <th className="px-4 py-2.5 text-right font-semibold">{t('platform.users')}</th>
                  <th className="px-4 py-2.5 text-right font-semibold">{t('platform.emp')}</th>
                  <th className="px-4 py-2.5 text-right font-semibold">{t('platform.cam')}</th>
                  <th className="px-4 py-2.5 text-left font-semibold">{t('platform.status')}</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {rows.map((ten) => (
                  <tr key={ten.id} className="border-t border-border/50">
                    <td className="px-4 py-2.5">
                      <span className="font-medium">{ten.name}</span>
                      <span className="ml-2 text-xs text-muted-foreground">
                        {ten.external_company_id ? t('platform.faceTrack') : t('platform.native')}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{ten.user_count}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{ten.employee_count}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{ten.camera_count}</td>
                    <td className="px-4 py-2.5">
                      {ten.is_active ? (
                        <Badge tone="success">{t('platform.active')}</Badge>
                      ) : (
                        <Badge tone="warning">{t('platform.suspendedTag')}</Badge>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="flex justify-end gap-1">
                        <IconBtn title={t('platform.enter')} onClick={() =>
                          enterTenant({ id: ten.id, name: ten.name }).catch(() => toast.error(t('common.error')))
                        }><LogIn className="h-4 w-4" /></IconBtn>
                        <IconBtn
                          title={ten.is_active ? t('platform.suspend') : t('platform.activate')}
                          onClick={() => toggleActive(ten)}
                        >{ten.is_active ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}</IconBtn>
                        <IconBtn title={t('common.edit')} onClick={() => setEditing(ten)}>
                          <Settings2 className="h-4 w-4" />
                        </IconBtn>
                        <IconBtn
                          title={t('common.delete')}
                          danger
                          disabled={ten.id === user?.tenant_id}
                          onClick={() => setDeleting(ten)}
                        ><Trash2 className="h-4 w-4" /></IconBtn>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {editing && <SettingsDialog tenant={editing} onClose={() => setEditing(null)} />}

      <Dialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t('platform.deleteTitle')}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleting(null)}>{t('common.cancel')}</Button>
            <Button
              variant="danger"
              disabled={deleting?.is_active}
              onClick={async () => {
                if (!deleting) return;
                try {
                  await del.mutateAsync(deleting.id);
                  toast.success(t('platform.deleted', { name: deleting.name }));
                } catch {
                  toast.error(t('common.error'));
                }
                setDeleting(null);
              }}
            >{t('common.delete')}</Button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">{t('platform.deleteConfirm', { name: deleting?.name })}</p>
        {deleting?.is_active && (
          <p className="mt-2 text-xs text-warning">{t('platform.suspendFirst')}</p>
        )}
      </Dialog>
    </div>
  );
}

function IconBtn({ children, title, onClick, danger, disabled }: {
  children: React.ReactNode; title: string; onClick: () => void; danger?: boolean; disabled?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={`rounded p-1.5 hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40 ${
        danger ? 'text-danger hover:bg-danger/10' : 'text-muted-foreground hover:text-foreground'
      }`}
    >
      {children}
    </button>
  );
}

function SettingsDialog({ tenant, onClose }: { tenant: PlatformTenant; onClose: () => void }) {
  const { t } = useTranslation();
  const update = useUpdateTenant();
  const [name, setName] = useState(tenant.name);
  const [tz, setTz] = useState(tenant.timezone);
  const [retention, setRetention] = useState(String(tenant.recording_retention_days));
  const [maxCameras, setMaxCameras] = useState(String(tenant.max_cameras || 0));

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={t('platform.editTitle', { name: tenant.name })}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
          <Button
            onClick={async () => {
              try {
                await update.mutateAsync({
                  id: tenant.id, name: name.trim(), timezone: tz.trim(),
                  recording_retention_days: Math.max(1, Number(retention) || 30),
                  max_cameras: Math.max(0, Number(maxCameras) || 0),
                });
                toast.success(t('platform.updated'));
                onClose();
              } catch { toast.error(t('common.error')); }
            }}
          >{t('common.save')}</Button>
        </>
      }
    >
      <div className="space-y-3">
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">{t('platform.name')}</span>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">{t('platform.timezone')}</span>
          <Input value={tz} onChange={(e) => setTz(e.target.value)} placeholder="UTC" />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">{t('platform.retention')}</span>
          <Input type="number" min={1} value={retention} onChange={(e) => setRetention(e.target.value)} />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">{t('platform.maxCameras')}</span>
          <Input type="number" min={0} value={maxCameras} onChange={(e) => setMaxCameras(e.target.value)} />
        </label>
      </div>
    </Dialog>
  );
}
