import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Upload, FileText } from 'lucide-react';
import { toast } from 'sonner';
import { Dialog } from '@/shared/components/Dialog';
import { Input } from '@/shared/components/Input';
import { Button } from '@/shared/components/Button';
import { Select } from '@/shared/components/Select';
import { useSites } from '@/modules/sites/api';
import { useUploadFloorPlan } from '@/modules/floor-plan/api';
import {
  ACCEPTED_EXTENSIONS,
  MAX_UPLOAD_BYTES,
} from '@/modules/floor-plan/types';

interface FloorPlanUploadDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  /** Optional pre-selected site (e.g. when launching from a site page). */
  initialSiteId?: string;
}

export function FloorPlanUploadDialog({
  open,
  onOpenChange,
  initialSiteId,
}: FloorPlanUploadDialogProps) {
  const { t } = useTranslation();
  const { data: sites } = useSites();
  const upload = useUploadFloorPlan();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [siteId, setSiteId] = useState<string>(initialSiteId || '');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Reset state on close
  useEffect(() => {
    if (!open) {
      setName('');
      setDescription('');
      setFile(null);
      setError(null);
      setSiteId(initialSiteId || '');
    }
  }, [open, initialSiteId]);

  // Default site picker to first site if none chosen
  useEffect(() => {
    if (!siteId && sites && sites.length > 0) {
      setSiteId(sites[0].id);
    }
  }, [sites, siteId]);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) {
      setFile(null);
      return;
    }
    if (f.size > MAX_UPLOAD_BYTES) {
      setError(
        t('floorPlan.upload.tooLarge', {
          limitMB: MAX_UPLOAD_BYTES / (1024 * 1024),
        })
      );
      return;
    }
    setError(null);
    setFile(f);
    // Auto-fill name from filename if empty
    if (!name) {
      const stem = f.name.replace(/\.[^.]+$/, '');
      setName(stem);
    }
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (!siteId) {
      setError(t('floorPlan.upload.siteRequired'));
      return;
    }
    if (!name.trim()) {
      setError(t('floorPlan.upload.nameRequired'));
      return;
    }
    if (!file) {
      setError(t('floorPlan.upload.fileRequired'));
      return;
    }

    try {
      await upload.mutateAsync({
        site_id: siteId,
        name: name.trim(),
        description: description.trim() || null,
        file,
      });
      toast.success(t('floorPlan.upload.success'));
      onOpenChange(false);
    } catch (err: any) {
      const raw = err?.response?.data?.detail;
      setError(
        typeof raw === 'string'
          ? raw
          : t('floorPlan.upload.failed')
      );
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('floorPlan.upload.title')}
      description={t('floorPlan.upload.subtitle')}
      size="md"
      footer={
        <>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={upload.isPending}
          >
            {t('common.cancel')}
          </Button>
          <Button onClick={onSubmit} disabled={upload.isPending}>
            {upload.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            <Upload className="h-4 w-4" />
            {t('floorPlan.upload.submit')}
          </Button>
        </>
      }
    >
      <form onSubmit={onSubmit} className="space-y-3">
        <Select
          label={t('floorPlan.upload.site')}
          name="site_id"
          value={siteId}
          onChange={(e) => setSiteId(e.target.value)}
          required
          options={(sites || []).map((s) => ({
            value: s.id,
            label: s.name,
          }))}
        />

        <Input
          label={t('floorPlan.upload.name')}
          name="name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t('floorPlan.upload.namePlaceholder')}
        />

        <Input
          label={t('floorPlan.upload.description')}
          name="description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />

        {/* File picker — a styled button rather than the ugly native input */}
        <div>
          <label className="mb-1.5 block text-sm font-medium text-foreground">
            {t('floorPlan.upload.file')}
          </label>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS}
            onChange={handleFileChange}
            className="hidden"
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex w-full items-center gap-3 rounded-md border border-dashed border-input bg-surface px-3 py-3 text-sm text-muted-foreground hover:border-primary hover:bg-primary/5"
          >
            <FileText className="h-5 w-5" />
            {file ? (
              <span className="flex-1 text-start">
                <span className="block text-foreground">{file.name}</span>
                <span className="text-xs text-muted-foreground">
                  {(file.size / 1024 / 1024).toFixed(2)} MB
                </span>
              </span>
            ) : (
              <span className="flex-1 text-start">
                {t('floorPlan.upload.filePlaceholder')}
              </span>
            )}
          </button>
          <p className="mt-1.5 text-xs text-muted-foreground">
            {t('floorPlan.upload.fileHint', {
              limitMB: MAX_UPLOAD_BYTES / (1024 * 1024),
            })}
          </p>
        </div>

        {error && (
          <div className="rounded-md border border-danger/30 bg-danger/10 p-2 text-xs text-danger">
            {error}
          </div>
        )}
      </form>
    </Dialog>
  );
}
