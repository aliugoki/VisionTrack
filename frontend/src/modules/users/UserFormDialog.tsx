import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/shared/components/Button';
import { Dialog } from '@/shared/components/Dialog';
import { Input } from '@/shared/components/Input';
import { Select } from '@/shared/components/Select';
import { useCreateUser, useRoles, useUpdateUser } from '@/modules/users/api';
import type { User } from '@/modules/users/types';

interface UserFormDialogProps {
  /** If provided, the dialog edits this user. If null, creates a new one. */
  user: User | null;
  open: boolean;
  onClose: () => void;
}

/**
 * Single dialog component used for both create + edit.
 * Create mode: shows email + password fields; submits via useCreateUser.
 * Edit mode: hides email + password; submits via useUpdateUser.
 *
 * Why one component instead of two:
 *   90% of the form is identical (name, locale, status, roles).
 *   Switching modes by a single prop (`user`) keeps a single source
 *   of truth for layout + validation logic.
 */
export function UserFormDialog({ user, open, onClose }: UserFormDialogProps) {
  const { t } = useTranslation();
  const isEdit = user !== null;

  const { data: roles = [] } = useRoles();
  const create = useCreateUser();
  const update = useUpdateUser(user?.id || '');
  const isPending = isEdit ? update.isPending : create.isPending;

  // Form state — reset on open + user change
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [locale, setLocale] = useState<'en' | 'ar'>('en');
  const [isActive, setIsActive] = useState(true);
  const [roleIds, setRoleIds] = useState<string[]>([]);

  useEffect(() => {
    if (!open) return;
    if (user) {
      setFullName(user.full_name);
      setEmail(user.email);
      setLocale(user.locale);
      setIsActive(user.is_active);
      setRoleIds(user.roles.map((r) => r.id));
      setPassword('');
    } else {
      setFullName('');
      setEmail('');
      setLocale('en');
      setIsActive(true);
      setRoleIds([]);
      setPassword('');
    }
  }, [open, user]);

  const toggleRole = (id: string) => {
    setRoleIds((prev) =>
      prev.includes(id) ? prev.filter((r) => r !== id) : [...prev, id]
    );
  };

  const handleSubmit = async () => {
    // Client-side validation: backend will validate too but we surface
    // friendlier messages without a round-trip.
    if (!fullName.trim()) {
      toast.error(t('users.form.nameRequired'));
      return;
    }
    if (!isEdit) {
      if (!email.trim()) {
        toast.error(t('users.form.emailRequired'));
        return;
      }
      if (password.length < 8) {
        toast.error(t('users.form.passwordTooShort'));
        return;
      }
    }
    try {
      if (isEdit) {
        await update.mutateAsync({
          full_name: fullName.trim(),
          locale,
          is_active: isActive,
          role_ids: roleIds,
        });
        toast.success(t('users.form.editSuccess'));
      } else {
        await create.mutateAsync({
          email: email.trim().toLowerCase(),
          full_name: fullName.trim(),
          password,
          locale,
          is_active: isActive,
          role_ids: roleIds,
        });
        toast.success(t('users.form.createSuccess'));
      }
      onClose();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      toast.error(
        typeof detail === 'string'
          ? detail
          : isEdit
            ? t('users.form.editError')
            : t('users.form.createError')
      );
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={isEdit ? t('users.form.editTitle') : t('users.form.createTitle')}
    >
      <div className="space-y-3">
        {/* Full name */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-foreground">
            {t('users.form.name')}
          </label>
          <Input
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            maxLength={255}
          />
        </div>

        {/* Email (create mode only — backend doesn't support email change) */}
        {!isEdit && (
          <div className="space-y-1">
            <label className="text-xs font-medium text-foreground">
              {t('users.form.email')}
            </label>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="off"
            />
          </div>
        )}

        {/* Password (create mode only — separate endpoint for changes) */}
        {!isEdit && (
          <div className="space-y-1">
            <label className="text-xs font-medium text-foreground">
              {t('users.form.password')}
            </label>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              minLength={8}
              maxLength={128}
            />
            <p className="text-xs text-muted-foreground">
              {t('users.form.passwordHelp')}
            </p>
          </div>
        )}

        {/* Locale */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-foreground">
            {t('users.form.locale')}
          </label>
          <Select
            value={locale}
            onChange={(e) => setLocale(e.target.value as 'en' | 'ar')}
          >
            <option value="en">English</option>
            <option value="ar">العربية</option>
          </Select>
        </div>

        {/* Active toggle */}
        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="user-active"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="h-4 w-4 rounded border-border"
          />
          <label
            htmlFor="user-active"
            className="text-xs font-medium text-foreground"
          >
            {t('users.form.active')}
          </label>
        </div>

        {/* Roles — multi-select via checkboxes */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-foreground">
            {t('users.form.roles')}
          </label>
          {roles.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              {t('users.form.noRoles')}
            </p>
          ) : (
            <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border border-border p-2">
              {roles.map((role) => (
                <label
                  key={role.id}
                  className="flex items-center gap-2 rounded px-1 py-0.5 hover:bg-muted/50"
                >
                  <input
                    type="checkbox"
                    checked={roleIds.includes(role.id)}
                    onChange={() => toggleRole(role.id)}
                    className="h-4 w-4 rounded border-border"
                  />
                  <span className="text-sm text-foreground">{role.name}</span>
                  {role.is_system && (
                    <span className="text-[10px] text-muted-foreground">
                      ({t('users.form.systemRole')})
                    </span>
                  )}
                </label>
              ))}
            </div>
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
