import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/shared/components/Button';
import { Dialog } from '@/shared/components/Dialog';
import { Input } from '@/shared/components/Input';
import { Spinner } from '@/shared/components/Spinner';
import {
  useCreateRole,
  usePermissionsCatalog,
  useUpdateRole,
} from '@/modules/roles/api';
import { PermissionMatrix } from '@/modules/roles/PermissionMatrix';
import type { Role } from '@/modules/roles/types';

interface RoleFormDialogProps {
  /** Edit mode if provided; otherwise create mode. */
  role: Role | null;
  open: boolean;
  onClose: () => void;
}

/**
 * Single dialog for create + edit.
 *
 * System role behavior (matches backend constraint):
 *   - Name is read-only (backend returns 400 if you try to rename)
 *   - Description is read-only (UX choice; backend allows but confusing)
 *   - Permissions ARE editable — that's the whole point of letting an
 *     admin tighten "Operator" for their org
 *
 * Custom role: everything editable.
 */
export function RoleFormDialog({ role, open, onClose }: RoleFormDialogProps) {
  const { t } = useTranslation();
  const isEdit = role !== null;
  const isSystem = role?.is_system ?? false;

  const { data: catalog, isLoading: catalogLoading } = usePermissionsCatalog();
  const create = useCreateRole();
  const update = useUpdateRole(role?.id || '');
  const isPending = isEdit ? update.isPending : create.isPending;

  // Form state
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [permissions, setPermissions] = useState<string[]>([]);

  // Reset form on open / role change
  useEffect(() => {
    if (!open) return;
    if (role) {
      setName(role.name);
      setDescription(role.description || '');
      setPermissions(role.permissions);
    } else {
      setName('');
      setDescription('');
      setPermissions([]);
    }
  }, [open, role]);

  const handleSubmit = async () => {
    if (!name.trim()) {
      toast.error(t('roles.form.nameRequired'));
      return;
    }
    if (permissions.length === 0) {
      toast.error(t('roles.form.permissionsRequired'));
      return;
    }
    try {
      if (isEdit && role) {
        // System role: only send permissions (name/description are read-only)
        const payload = isSystem
          ? { permissions }
          : {
              name: name.trim(),
              description: description.trim() || null,
              permissions,
            };
        await update.mutateAsync(payload);
        toast.success(t('roles.form.editSuccess'));
      } else {
        await create.mutateAsync({
          name: name.trim(),
          description: description.trim() || null,
          permissions,
        });
        toast.success(t('roles.form.createSuccess'));
      }
      onClose();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      toast.error(
        typeof detail === 'string'
          ? detail
          : isEdit
            ? t('roles.form.editError')
            : t('roles.form.createError')
      );
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={isEdit ? t('roles.form.editTitle') : t('roles.form.createTitle')}
    >
      <div className="space-y-3">
        {/* Name */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-foreground">
            {t('roles.form.name')}
          </label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={isSystem}
            maxLength={100}
          />
          {isSystem && (
            <p className="text-xs text-muted-foreground">
              {t('roles.form.systemNameReadonly')}
            </p>
          )}
        </div>

        {/* Description */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-foreground">
            {t('roles.form.description')}
          </label>
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={isSystem}
            maxLength={500}
          />
        </div>

        {/* Permission matrix */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-foreground">
            {t('roles.form.permissions')}
          </label>
          {catalogLoading || !catalog ? (
            <div className="flex items-center justify-center py-8">
              <Spinner size={20} />
            </div>
          ) : (
            <PermissionMatrix
              catalog={catalog}
              selected={permissions}
              onChange={setPermissions}
            />
          )}
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 border-t border-border pt-3">
          <Button variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button onClick={handleSubmit} disabled={isPending}>
            {isPending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : null}
            {isEdit ? t('common.save') : t('common.create')}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
