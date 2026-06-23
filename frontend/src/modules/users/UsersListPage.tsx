import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Loader2,
  Pencil,
  Plus,
  Search,
  Trash2,
  UserCog,
  UserX,
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
  USER_CREATE,
  USER_DELETE,
  USER_UPDATE,
} from '@/shared/lib/permissions';
import { useDeleteUser, useUsers } from '@/modules/users/api';
import { UserFormDialog } from '@/modules/users/UserFormDialog';
import type { User } from '@/modules/users/types';

export default function UsersListPage() {
  const { t } = useTranslation();
  const { hasPermission, user: me } = useAuth();
  const canCreate = hasPermission(USER_CREATE);
  const canEdit = hasPermission(USER_UPDATE);
  const canDelete = hasPermission(USER_DELETE);

  const { data: users = [], isLoading } = useUsers();
  const deleteUser = useDeleteUser();

  const [search, setSearch] = useState('');
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [creatingUser, setCreatingUser] = useState(false);
  const [deletingUser, setDeletingUser] = useState<User | null>(null);

  // Filter on lowercased substring across name + email + role names
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return users;
    return users.filter(
      (u) =>
        u.full_name.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q) ||
        u.roles.some((r) => r.name.toLowerCase().includes(q))
    );
  }, [users, search]);

  const handleDelete = async () => {
    if (!deletingUser) return;
    try {
      await deleteUser.mutateAsync(deletingUser.id);
      toast.success(t('users.delete.success'));
      setDeletingUser(null);
    } catch (e: any) {
      toast.error(
        e?.response?.data?.detail || t('users.delete.error')
      );
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-foreground">
            <UserCog className="h-6 w-6" />
            {t('users.title')}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t('users.subtitle')}
          </p>
        </div>
        {canCreate && (
          <Button onClick={() => setCreatingUser(true)}>
            <Plus className="h-3 w-3" />
            {t('users.actions.add')}
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
            placeholder={t('users.searchPlaceholder')}
            className="flex-1"
          />
          <div className="text-xs text-muted-foreground">
            {t('users.counter', {
              shown: filtered.length,
              total: users.length,
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
          <UserX className="h-8 w-8 text-muted-foreground/50" />
          <p className="text-sm font-medium text-foreground">
            {search ? t('users.empty.searchTitle') : t('users.empty.title')}
          </p>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/40">
                <tr>
                  <th className="px-3 py-2 text-start font-medium text-muted-foreground">
                    {t('users.col.name')}
                  </th>
                  <th className="px-3 py-2 text-start font-medium text-muted-foreground">
                    {t('users.col.email')}
                  </th>
                  <th className="px-3 py-2 text-start font-medium text-muted-foreground">
                    {t('users.col.roles')}
                  </th>
                  <th className="px-3 py-2 text-start font-medium text-muted-foreground">
                    {t('users.col.status')}
                  </th>
                  <th className="px-3 py-2 text-end font-medium text-muted-foreground">
                    {t('users.col.actions')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((u) => (
                  <tr
                    key={u.id}
                    className="border-b border-border last:border-0 hover:bg-muted/20"
                  >
                    <td className="px-3 py-2 font-medium text-foreground">
                      {u.full_name}
                      {u.is_superuser && (
                        <Badge tone="warning" className="ms-1">
                          {t('users.superuser')}
                        </Badge>
                      )}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">
                      {u.email}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        {u.roles.length === 0 ? (
                          <span className="text-xs text-muted-foreground">
                            —
                          </span>
                        ) : (
                          u.roles.map((r) => (
                            <Badge key={r.id} tone="neutral">
                              {r.name}
                            </Badge>
                          ))
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <Badge tone={u.is_active ? 'success' : 'neutral'}>
                        {u.is_active
                          ? t('users.status.active')
                          : t('users.status.inactive')}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-end">
                      <div className="flex items-center justify-end gap-1">
                        {canEdit && (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setEditingUser(u)}
                            title={t('users.actions.edit')}
                          >
                            <Pencil className="h-3 w-3" />
                          </Button>
                        )}
                        {canDelete && u.id !== me?.id && (
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => setDeletingUser(u)}
                            title={t('users.actions.delete')}
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
      <UserFormDialog
        user={editingUser}
        open={editingUser !== null || creatingUser}
        onClose={() => {
          setEditingUser(null);
          setCreatingUser(false);
        }}
      />

      {/* Delete confirm */}
      <Dialog
        open={deletingUser !== null}
        onClose={() => setDeletingUser(null)}
        title={t('users.delete.title')}
      >
        <div className="space-y-3">
          <p className="text-sm text-foreground">
            {t('users.delete.confirm', { name: deletingUser?.full_name })}
          </p>
          <p className="text-xs text-muted-foreground">
            {t('users.delete.warning')}
          </p>
          <div className="flex justify-end gap-2 border-t border-border pt-3">
            <Button variant="ghost" onClick={() => setDeletingUser(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteUser.isPending}
            >
              {deleteUser.isPending ? (
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
