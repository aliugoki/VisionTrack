import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { useAuth } from '@/shared/hooks/useAuth';

const API_BASE = '/api/v1';

export const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

// Attach access token to every request
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuth.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Refresh token flow — if a request 401s, try the refresh token once.
// Multiple concurrent failures share a single in-flight refresh promise so
// we don't make N refresh calls at the same time.
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = useAuth.getState().refreshToken;
  if (!refreshToken) return null;

  try {
    const { data } = await axios.post(`${API_BASE}/auth/refresh`, {
      refresh_token: refreshToken,
    });
    useAuth.getState().setTokens(data.access_token, data.refresh_token);
    return data.access_token;
  } catch {
    useAuth.getState().clear();
    return null;
  }
}

api.interceptors.response.use(
  (resp) => resp,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;

      refreshPromise = refreshPromise ?? refreshAccessToken();
      const newToken = await refreshPromise;
      refreshPromise = null;

      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`;
        return api.request(original);
      }
    }

    return Promise.reject(error);
  }
);
