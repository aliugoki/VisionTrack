import { Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Logo } from '@/shared/components/Logo';
import { LanguageSwitcher } from '@/shared/components/LanguageSwitcher';

export function AuthLayout() {
  const { t } = useTranslation();

  return (
    <div className="relative min-h-screen overflow-hidden bg-background">
      {/* Atmospheric backdrop — subtle grid + radial glow */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            'linear-gradient(hsl(var(--foreground)) 1px, transparent 1px),' +
            'linear-gradient(90deg, hsl(var(--foreground)) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
        }}
      />
      <div
        className="pointer-events-none absolute -top-40 left-1/2 h-[600px] w-[800px] -translate-x-1/2 rounded-full opacity-20 blur-3xl"
        style={{ background: 'radial-gradient(circle, hsl(var(--primary)) 0%, transparent 70%)' }}
      />

      <div className="absolute end-6 top-6 z-10">
        <LanguageSwitcher />
      </div>

      <div className="relative z-10 flex min-h-screen items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-3">
            <Logo className="h-10 w-10" />
            <div>
              <div className="text-lg font-semibold tracking-tight text-foreground">
                {t('app.name')}
              </div>
              <div className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
                {t('app.tagline')}
              </div>
            </div>
          </div>
          <Outlet />
        </div>
      </div>
    </div>
  );
}
