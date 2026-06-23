import { useTranslation } from 'react-i18next';
import { Construction } from 'lucide-react';

export default function ModulePlaceholder({ name }: { name: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex h-full min-h-[60vh] items-center justify-center">
      <div className="max-w-md text-center">
        <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-muted">
          <Construction className="h-8 w-8 text-muted-foreground" />
        </div>
        <h2 className="mb-2 text-xl font-semibold text-foreground">{name}</h2>
        <p className="text-sm text-muted-foreground">{t('common.comingSoon')}</p>
        <p className="mt-4 font-mono text-xs text-muted-foreground">
          {t('common.module')} · {name.toLowerCase().replace(/\s+/g, '-')}
        </p>
      </div>
    </div>
  );
}
