import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Mail, Lock, ArrowRight } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/shared/components/Button';
import { Input } from '@/shared/components/Input';
import { Card, CardContent } from '@/shared/components/Card';
import { useAuth, type CurrentUser } from '@/shared/hooks/useAuth';
import { api } from '@/shared/api/client';

export default function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { setTokens, setUser } = useAuth();

  const [email, setEmail] = useState('admin@visiontrack.io');
  const [password, setPassword] = useState('ChangeMe123!');
  const [tenant, setTenant] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const { data } = await api.post<{
        access_token: string;
        refresh_token: string;
      }>('/auth/login', {
        email: email.trim().toLowerCase(),
        password,
        tenant_subdomain: tenant.trim() || undefined,
      });
      setTokens(data.access_token, data.refresh_token);

      const me = await api.get<CurrentUser>('/users/me');
      setUser(me.data);

      toast.success(t('auth.loginSuccess'));
      navigate('/', { replace: true });
    } catch (err: any) {
      // FastAPI returns either {detail: "string"} (e.g. 401) or
      // {detail: [{msg: "...", loc: [...]}]} (422 validation errors).
      const raw = err?.response?.data?.detail;
      let message: string;
      if (typeof raw === 'string') {
        message = raw;
      } else if (Array.isArray(raw) && raw.length > 0) {
        message = raw
          .map((e: any) => {
            const field = Array.isArray(e.loc) ? e.loc[e.loc.length - 1] : '';
            return field ? `${field}: ${e.msg}` : e.msg;
          })
          .join('; ');
      } else {
        message = t('auth.invalidCredentials');
      }
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card>
      <CardContent className="space-y-6 p-7">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            {t('auth.welcomeBack')}
          </h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {t('auth.signInPrompt')}
          </p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <Input
            type="email"
            name="email"
            autoComplete="email"
            required
            label={t('auth.email')}
            leftIcon={<Mail className="h-4 w-4" />}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Input
            type="password"
            name="password"
            autoComplete="current-password"
            required
            label={t('auth.password')}
            leftIcon={<Lock className="h-4 w-4" />}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <Input
            type="text"
            name="tenant"
            label={t('auth.tenantSubdomain')}
            hint={t('auth.tenantSubdomainHelp')}
            placeholder="acme"
            value={tenant}
            onChange={(e) => setTenant(e.target.value.toLowerCase())}
          />

          {error && (
            <div className="rounded-md border border-danger/30 bg-danger/10 p-3 text-sm text-danger">
              {error}
            </div>
          )}

          <Button
            type="submit"
            size="lg"
            disabled={submitting}
            className="w-full"
          >
            {submitting ? t('auth.signingIn') : t('auth.signIn')}
            {!submitting && <ArrowRight className="h-4 w-4" />}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
