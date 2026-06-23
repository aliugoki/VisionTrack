import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Radio, Search, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Dialog } from '@/shared/components/Dialog';
import { Input } from '@/shared/components/Input';
import { Select } from '@/shared/components/Select';
import { Button } from '@/shared/components/Button';
import { Badge } from '@/shared/components/Badge';
import { useSites } from '@/modules/sites/api';
import {
  useCreateCamera,
  useDiscoverCameras,
  useUpdateCamera,
} from '@/modules/cameras/api';
import type { Camera, CameraDiscoveryResult } from '@/shared/types/api';

interface CameraFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** If provided, the dialog is in edit mode. */
  camera?: Camera;
}

interface FormState {
  name: string;
  description: string;
  site_id: string;
  rtsp_url: string;
  is_recording: boolean;
}

const INITIAL: FormState = {
  name: '',
  description: '',
  site_id: '',
  rtsp_url: '',
  is_recording: true,
};

export function CameraFormDialog({
  open,
  onOpenChange,
  camera,
}: CameraFormDialogProps) {
  const { t } = useTranslation();
  const isEdit = !!camera;

  const { data: sites } = useSites();
  const createMutation = useCreateCamera();
  const updateMutation = useUpdateCamera(camera?.id || '');

  const [form, setForm] = useState<FormState>(INITIAL);
  const [showDiscovery, setShowDiscovery] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);

  // Reset form when the dialog opens / switches cameras
  useEffect(() => {
    if (!open) return;
    if (camera) {
      setForm({
        name: camera.name,
        description: camera.description ?? '',
        site_id: camera.site_id,
        // Edit mode: don't prefill the (masked) URL — user must re-enter
        // if they want to change it, otherwise leaves it untouched.
        rtsp_url: '',
        is_recording: camera.is_recording,
      });
    } else {
      setForm({
        ...INITIAL,
        site_id: sites?.[0]?.id ?? '',
      });
    }
    setFieldErrors({});
    setServerError(null);
    setShowDiscovery(false);
  }, [open, camera, sites]);

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (form.name.trim().length < 2) errs.name = 'Name must be at least 2 characters';
    if (!form.site_id) errs.site_id = 'Please choose a site';

    // RTSP URL is required on create, optional on edit (only if changing)
    if (!isEdit) {
      const url = form.rtsp_url.trim();
      if (!url) {
        errs.rtsp_url = 'RTSP URL is required';
      } else if (!url.startsWith('rtsp://') && !url.startsWith('rtsps://')) {
        errs.rtsp_url = 'Must start with rtsp:// or rtsps://';
      }
    } else if (form.rtsp_url.trim()) {
      const url = form.rtsp_url.trim();
      if (!url.startsWith('rtsp://') && !url.startsWith('rtsps://')) {
        errs.rtsp_url = 'Must start with rtsp:// or rtsps://';
      }
    }

    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setServerError(null);
    if (!validate()) return;

    try {
      if (isEdit && camera) {
        await updateMutation.mutateAsync({
          name: form.name.trim(),
          description: form.description.trim() || null,
          is_recording: form.is_recording,
          // Only send rtsp_url if user typed a new one
          ...(form.rtsp_url.trim() ? { rtsp_url: form.rtsp_url.trim() } : {}),
        });
        toast.success(t('cameras.toast.updated'));
      } else {
        await createMutation.mutateAsync({
          name: form.name.trim(),
          description: form.description.trim() || null,
          site_id: form.site_id,
          rtsp_url: form.rtsp_url.trim(),
          is_recording: form.is_recording,
        });
        toast.success(t('cameras.toast.created'));
      }
      onOpenChange(false);
    } catch (err: any) {
      const raw = err?.response?.data?.detail;
      const message =
        typeof raw === 'string'
          ? raw
          : Array.isArray(raw) && raw.length > 0
          ? raw.map((e: any) => `${e.loc?.slice(-1)[0] || ''}: ${e.msg}`).join('; ')
          : 'Something went wrong';
      setServerError(message);
    }
  }

  const submitting = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="md"
      title={isEdit ? t('cameras.editTitle') : t('cameras.addTitle')}
      description={
        isEdit
          ? t('cameras.editSubtitle')
          : t('cameras.addSubtitle')
      }
      footer={
        <>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            {t('common.cancel')}
          </Button>
          <Button onClick={onSubmit} disabled={submitting}>
            {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {isEdit ? t('common.save') : t('common.create')}
          </Button>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" id="camera-form">
        <Input
          label={t('cameras.fields.name')}
          name="name"
          required
          autoFocus
          value={form.name}
          error={fieldErrors.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
        />

        <Select
          label={t('cameras.fields.site')}
          name="site_id"
          required
          disabled={isEdit}
          value={form.site_id}
          error={fieldErrors.site_id}
          onChange={(e) => setForm({ ...form, site_id: e.target.value })}
          placeholder={t('cameras.fields.sitePlaceholder')}
          options={(sites || []).map((s) => ({
            value: s.id,
            label: s.name,
          }))}
        />

        <Input
          label={t('cameras.fields.rtspUrl')}
          name="rtsp_url"
          required={!isEdit}
          placeholder={
            isEdit
              ? t('cameras.fields.rtspUrlPlaceholderEdit')
              : 'rtsp://user:pass@192.168.1.10:554/Streaming/Channels/101'
          }
          hint={
            isEdit
              ? t('cameras.fields.rtspUrlHintEdit')
              : t('cameras.fields.rtspUrlHint')
          }
          value={form.rtsp_url}
          error={fieldErrors.rtsp_url}
          onChange={(e) => setForm({ ...form, rtsp_url: e.target.value })}
        />

        <Input
          label={t('cameras.fields.description')}
          name="description"
          value={form.description}
          onChange={(e) =>
            setForm({ ...form, description: e.target.value })
          }
        />

        <label className="flex items-center gap-2 pt-1">
          <input
            type="checkbox"
            checked={form.is_recording}
            onChange={(e) =>
              setForm({ ...form, is_recording: e.target.checked })
            }
            className="h-4 w-4 rounded border-input bg-surface text-primary focus:ring-2 focus:ring-ring"
          />
          <span className="text-sm text-foreground">
            {t('cameras.fields.isRecording')}
          </span>
        </label>

        {serverError && (
          <div className="rounded-md border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
            {serverError}
          </div>
        )}

        {!isEdit && (
          <div className="rounded-md border border-border bg-muted/40 p-3">
            <button
              type="button"
              onClick={() => setShowDiscovery((v) => !v)}
              className="flex w-full items-center justify-between text-sm font-medium text-foreground"
            >
              <span className="flex items-center gap-2">
                <Radio className="h-4 w-4" />
                {t('cameras.discover.title')}
              </span>
              <span className="text-xs text-muted-foreground">
                {showDiscovery ? '−' : '+'}
              </span>
            </button>
            {showDiscovery && (
              <DiscoveryPanel
                onSelect={(r) =>
                  setForm((f) => ({
                    ...f,
                    rtsp_url:
                      r.suggested_rtsp_url ||
                      `rtsp://${r.ip}:554/Streaming/Channels/101`,
                    name:
                      f.name ||
                      `${r.manufacturer || 'Camera'} ${r.ip}`,
                  }))
                }
              />
            )}
          </div>
        )}
      </form>
    </Dialog>
  );
}

// -- ONVIF discovery panel ------------------------------------------------------
function DiscoveryPanel({
  onSelect,
}: {
  onSelect: (result: CameraDiscoveryResult) => void;
}) {
  const { t } = useTranslation();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const discover = useDiscoverCameras();

  async function run() {
    try {
      await discover.mutateAsync({
        username: username || undefined,
        password: password || undefined,
        timeout_seconds: 5,
      });
    } catch {
      toast.error(t('cameras.discover.failed'));
    }
  }

  return (
    <div className="mt-3 space-y-3">
      <p className="text-xs text-muted-foreground">
        {t('cameras.discover.hint')}
      </p>
      <div className="grid grid-cols-2 gap-2">
        <Input
          name="onvif_user"
          placeholder={t('cameras.discover.username')}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <Input
          name="onvif_pass"
          type="password"
          placeholder={t('cameras.discover.password')}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        onClick={run}
        disabled={discover.isPending}
        className="w-full"
      >
        {discover.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Search className="h-4 w-4" />
        )}
        {discover.isPending
          ? t('cameras.discover.scanning')
          : t('cameras.discover.scan')}
      </Button>

      {discover.data && discover.data.length === 0 && (
        <p className="text-xs text-warning">
          {t('cameras.discover.empty')}
        </p>
      )}

      {discover.data && discover.data.length > 0 && (
        <ul className="scrollbar-thin max-h-48 space-y-1.5 overflow-y-auto">
          {discover.data.map((r) => (
            <li key={r.xaddr}>
              <button
                type="button"
                onClick={() => onSelect(r)}
                className="flex w-full items-start justify-between gap-2 rounded-md border border-border bg-surface p-2 text-start text-sm transition-colors hover:border-primary hover:bg-primary/5"
              >
                <div className="min-w-0 flex-1">
                  <div className="font-medium text-foreground">
                    {r.manufacturer || 'Unknown'} {r.model || ''}
                  </div>
                  <div className="font-mono text-xs text-muted-foreground">
                    {r.ip}:{r.port}
                  </div>
                </div>
                {r.suggested_rtsp_url ? (
                  <Badge tone="success">RTSP</Badge>
                ) : (
                  <Badge tone="neutral">{t('cameras.discover.needsCreds')}</Badge>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
