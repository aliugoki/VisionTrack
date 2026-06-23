import { useTranslation } from 'react-i18next';
import { Languages } from 'lucide-react';
import { cn } from '@/shared/lib/cn';

export function LanguageSwitcher({ className }: { className?: string }) {
  const { i18n, t } = useTranslation();

  const toggle = () => {
    const next = i18n.language === 'en' ? 'ar' : 'en';
    void i18n.changeLanguage(next);
  };

  return (
    <button
      type="button"
      onClick={toggle}
      className={cn(
        'inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm font-medium',
        'text-muted-foreground transition-colors hover:bg-muted hover:text-foreground',
        className
      )}
      aria-label={t('common.language')}
    >
      <Languages className="h-4 w-4" />
      <span>{i18n.language === 'en' ? t('common.arabic') : t('common.english')}</span>
    </button>
  );
}
