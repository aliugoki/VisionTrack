import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Building2, Plus, Pencil, Trash2, RefreshCw } from 'lucide-react';
import { Card } from '@/shared/components/Card';
import { Button } from '@/shared/components/Button';
import { Input } from '@/shared/components/Input';
import { Badge } from '@/shared/components/Badge';
import { Spinner } from '@/shared/components/Spinner';
import { Dialog } from '@/shared/components/Dialog';
import { useAuth } from '@/shared/hooks/useAuth';
import { TENANT_UPDATE } from '@/shared/lib/permissions';
import {
  useCompanies,
  useCreateCompany,
  useUpdateCompany,
  useDeleteCompany,
  type Company,
} from '@/modules/companies/api';

/**
 * Companies — reflected from FaceTrack (source=facetrack) plus VisionTrack-native
 * ones. Managed here (create / edit / delete); FaceTrack stays the source of
 * truth for reflected fields, so a re-sync will overwrite edits to those.
 */
export default function CompaniesPage() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canManage = hasPermission(TENANT_UPDATE);
  const { data, isLoading } = useCompanies();
  const rows = data?.rows ?? [];

  const [editing, setEditing] = useState<Company | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<Company | null>(null);
  const del = useDeleteCompany();

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-foreground">
            <Building2 className="h-6 w-6" />
            {t('companies.title')}
          </h1>
          <p className="text-sm text-muted-foreground">{t('companies.subtitle')}</p>
        </div>
        {canManage && (
          <Button onClick={() => setCreating(true)}>
            <Plus className="mr-1 h-4 w-4" />
            {t('companies.add')}
          </Button>
        )}
      </div>

      <Card className="overflow-hidden p-0">
        {isLoading ? (
          <div className="p-8">
            <Spinner />
          </div>
        ) : rows.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">{t('companies.empty')}</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 text-left font-semibold">{t('companies.name')}</th>
                  <th className="px-4 py-2.5 text-left font-semibold">{t('companies.admin')}</th>
                  <th className="px-4 py-2.5 text-right font-semibold">{t('companies.employees')}</th>
                  <th className="px-4 py-2.5 text-left font-semibold">{t('companies.source')}</th>
                  <th className="px-4 py-2.5 text-left font-semibold">{t('companies.active')}</th>
                  {canManage && <th className="px-4 py-2.5" />}
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} className="border-t border-border/50">
                    <td className="px-4 py-2.5 font-medium">{c.name}</td>
                    <td className="px-4 py-2.5 text-muted-foreground">{c.admin_username || '—'}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{c.employee_count}</td>
                    <td className="px-4 py-2.5">
                      <Badge tone={c.source === 'facetrack' ? 'neutral' : 'success'}>
                        {c.source === 'facetrack' ? t('companies.faceTrack') : t('companies.native')}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`inline-block h-2.5 w-2.5 rounded-full ${c.is_active ? 'bg-success' : 'bg-muted-foreground/40'}`} />
                    </td>
                    {canManage && (
                      <td className="px-4 py-2.5">
                        <span className="flex justify-end gap-1">
                          <button
                            type="button"
                            className="rounded p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
                            title={t('common.edit')}
                            onClick={() => setEditing(c)}
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            className="rounded p-1.5 text-danger hover:bg-danger/10"
                            title={t('common.delete')}
                            onClick={() => setDeleting(c)}
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </span>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {(creating || editing) && (
        <CompanyFormDialog
          company={editing}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}

      <Dialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t('companies.deleteTitle')}
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="danger"
              onClick={async () => {
                if (!deleting) return;
                try {
                  await del.mutateAsync(deleting.id);
                  toast.success(t('companies.deleted'));
                } catch {
                  toast.error(t('common.error'));
                }
                setDeleting(null);
              }}
            >
              {t('common.delete')}
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted-foreground">
          {t('companies.deleteConfirm', { name: deleting?.name })}
        </p>
        {deleting?.source === 'facetrack' && (
          <p className="mt-2 flex items-center gap-1.5 text-xs text-warning">
            <RefreshCw className="h-3.5 w-3.5" />
            {t('companies.resyncNote')}
          </p>
        )}
      </Dialog>
    </div>
  );
}

function CompanyFormDialog({ company, onClose }: { company: Company | null; onClose: () => void }) {
  const { t } = useTranslation();
  const isEdit = !!company;
  const create = useCreateCompany();
  const update = useUpdateCompany(company?.id ?? '');
  const [name, setName] = useState(company?.name ?? '');
  const [admin, setAdmin] = useState(company?.admin_username ?? '');
  const [active, setActive] = useState(company?.is_active ?? true);

  useEffect(() => {
    setName(company?.name ?? '');
    setAdmin(company?.admin_username ?? '');
    setActive(company?.is_active ?? true);
  }, [company]);

  const submit = async () => {
    if (!name.trim()) return;
    try {
      const payload = { name: name.trim(), admin_username: admin.trim() || null, is_active: active };
      if (isEdit) await update.mutateAsync(payload);
      else await create.mutateAsync(payload);
      toast.success(isEdit ? t('companies.updated') : t('companies.created'));
      onClose();
    } catch {
      toast.error(t('common.error'));
    }
  };

  return (
    <Dialog
      open
      onOpenChange={(o) => !o && onClose()}
      title={isEdit ? t('companies.editTitle') : t('companies.addTitle')}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button onClick={submit} disabled={!name.trim() || create.isPending || update.isPending}>
            {t('common.save')}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">{t('companies.name')}</span>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t('companies.name')} />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-muted-foreground">{t('companies.admin')}</span>
          <Input value={admin} onChange={(e) => setAdmin(e.target.value)} placeholder={t('companies.admin')} />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          {t('companies.active')}
        </label>
        {isEdit && company?.source === 'facetrack' && (
          <p className="text-xs text-warning">{t('companies.editSyncNote')}</p>
        )}
      </div>
    </Dialog>
  );
}
