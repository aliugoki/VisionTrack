import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Loader2,
  Pencil,
  Plus,
  Search,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/shared/components/Badge';
import { Button } from '@/shared/components/Button';
import { Card } from '@/shared/components/Card';
import { Dialog } from '@/shared/components/Dialog';
import { Input } from '@/shared/components/Input';
import { Spinner } from '@/shared/components/Spinner';
import { useAuth } from '@/shared/hooks/useAuth';
import {
  ROLE_CREATE,
  ROLE_DELETE,
  ROLE_UPDATE,
} from '@/shared/lib/permissions';
import { useDeleteRole, useRoles } from '@/modules/roles/api';
import { RoleFormDialog } from '@/modules/roles/RoleFormDialog';
import type { Role } from '@/modules/roles/types';

export default function RolesListPage() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canCreate = hasPermission(ROLE_CREATE);
  const canEdit = hasPermission(ROLE_UPDATE);
  const canDelete = hasPermission(ROLE_DELETE);

  const { data: roles = [], isLoading } = useRoles();
  const deleteRole = useDeleteRole();

  const [search, setSearch] = useState('');
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Role | null>(null);
  const [deleting, setDeleting] = useState<Role | null>(null);

  // Filter by name + description substring (case-insensitive)
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return roles;
    return roles.filter(
      (r) =>
        r.name.toLowerCase().includes(q) ||
        (r.description || '').toLowerCase().includes(q)
    );
  }, [roles, search]);

  const handleDelete = async () => {
    if (!deleting) return;
    try {
      await deleteRole.mutateAsync(deleting.id);
      toast.success(t('roles.delete.success'));
      setDeleting(null);
    } catch (e: any) {
      // Backend returns 409 if role has assigned users — surface the detail
      toast.error(e?.response?.data?.detail || t('roles.delete.error'));
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-foreground">
            <ShieldCheck className="h-6 w-6" />
            {t('roles.title')}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t('roles.subtitle')}
          </p>
        </div>
        {canCreate && (
          <Button onClick={() => setCreating(true)}>
            <Plus className="h-3 w-3" />
            {t('roles.actions.add')}
          </Button>
        )}
      </div>

      {/* Search */}
      <Card className="p-3">
        <div className="flex items-center gap-2">
          <Search className="h-3.5 w-3.5 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('roles.searchPlaceholder')}
            className="flex-1"
          />
          <div className="text-xs text-muted-foreground">
            {t('roles.counter', {
              shown: filtered.length,
              total: roles.length,
            })}
          </div>
        </div>
      </Card>

      {/* Body */}
      {isLoading ? (
        <Card className="flex items-center justify-center p-12">
          <Spinner size={24} />
        </Card>
      ) : filtered.length === 0 ? (
        <Card className="flex flex-col items-center justify-center gap-2 p-12 text-center">
          <ShieldCheck className="h-8 w-8 text-muted-foreground/50" />
          <p className="text-sm font-medium text-foreground">
            {search ? t('roles.empty.searchTitle') : t('roles.empty.title')}
          </p>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/40">
                <tr>
                  <th className="px-3 py-2 text-start font-medium text-muted-foreground">
                    {t('roles.col.name')}
                  </th>
                  <th className="px-3 py-2 text-start font-medium text-muted-foreground">
                    {t('roles.col.description')}
                  </th>
                  <th className="px-3 py-2 text-start font-medium text-muted-foreground">
                    {t('roles.col.permissions')}
                  </th>
                  <th className="px-3 py-2 text-start font-medium text-muted-foreground">
                    {t('roles.col.type')}
                  </th>
                  <th className="px-3 py-2 text-end font-medium text-muted-foreground">
                    {t('roles.col.actions')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr
                    key={r.id}
                    className="border-b border-border last:border-0 hover:bg-muted/20"
                  >
                    <td className="px-3 py-2 font-medium text-foreground">
                      {r.name}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {r.description || (
                        <span className="text-muted-foreground/50">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <Badge tone="neutral">
                        {t('roles.permissionsCount', {
                          n: r.permissions.length,
                        })}
                      </Badge>
                    </td>
                    <td className="px-3 py-2">
                      <Badge tone={r.is_system ? 'warning' : 'success'}>
                        {r.is_system
                          ? t('roles.type.system')
                          : t('roles.type.custom')}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-end">
                      <div className="flex items-center justify-end gap-1">
                        {canEdit && (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setEditing(r)}
                            title={t('roles.actions.edit')}
                          >
                            <Pencil className="h-3 w-3" />
                          </Button>
                        )}
                        {canDelete && !r.is_system && (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setDeleting(r)}
                            title={t('roles.actions.delete')}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Create / Edit dialog */}
      <RoleFormDialog
        role={editing}
        open={editing !== null || creating}
        onClose={() => {
          setEditing(null);
          setCreating(false);
        }}
      />

      {/* Delete confirm */}
      <Dialog
        open={deleting !== null}
        onClose={() => setDeleting(null)}
        title={t('roles.delete.title')}
      >
        <div className="space-y-3">
          <p className="text-sm text-foreground">
            {t('roles.delete.confirm', { name: deleting?.name })}
          </p>
          <p className="text-xs text-muted-foreground">
            {t('roles.delete.warning')}
          </p>
          <div className="flex justify-end gap-2 border-t border-border pt-3">
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteRole.isPending}
            >
              {deleteRole.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Trash2 className="h-3 w-3" />
              )}
              {t('common.delete')}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
