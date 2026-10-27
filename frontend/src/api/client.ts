import axios, { type AxiosRequestConfig } from 'axios'

export function getApiErrorStatus(error: unknown): number | undefined {
  if (axios.isAxiosError(error)) return error.response?.status
  if (typeof error === 'object' && error !== null && 'status' in error && typeof error.status === 'number') {
    return error.status
  }
}

type ApiClient = {
  get: <T = unknown>(url: string, config?: AxiosRequestConfig) => Promise<T>
  post: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) => Promise<T>
  put: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) => Promise<T>
  patch: <T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig) => Promise<T>
  delete: <T = unknown>(url: string, config?: AxiosRequestConfig) => Promise<T>
}

/** Convert the structured error envelopes returned by v2 into safe UI text. */
export function formatApiError(error: unknown, fallback = 'Request failed'): string {
  const value = error as {
    response?: { data?: { detail?: unknown } };
    detail?: unknown;
    message?: unknown;
  } | null | undefined
  const detail = value?.response?.data?.detail ?? value?.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object') {
    const item = detail as { message?: unknown; error?: unknown; next_action?: unknown }
    const message = typeof item.message === 'string' ? item.message : ''
    const code = typeof item.error === 'string' ? item.error : ''
    const next = typeof item.next_action === 'string' ? item.next_action : ''
    return [code, message, next].filter(Boolean).join(': ') || fallback
  }
  if (typeof value?.message === 'string' && value.message.trim()) return value.message
  return fallback
}

function createApiClient(baseURL: string): ApiClient {
  const client = axios.create({ baseURL })
  client.interceptors.response.use(
    res => res.data != null && typeof res.data === 'object' && res.data.data !== undefined ? res.data.data : res.data,
    (err: unknown) => {
      if (!axios.isAxiosError<unknown>(err)) return Promise.reject(err)
      const status = err.response?.status
      const data = err.response?.data
      const payload = typeof data === 'object' && data !== null ? data : undefined
      // Preserve the existing top-level detail contract for callers while
      // retaining the HTTP status for error-state decisions.
      return Promise.reject(payload ? { ...payload, status } : err)
    }
  )
  // The success interceptor above unwraps AxiosResponse at runtime. Axios 2's
  // public types intentionally keep the original response type, so centralize
  // that boundary instead of leaking casts through every API call site.
  const data = <T>(request: Promise<unknown>) => request as Promise<T>
  return {
    get: <T>(url: string, config?: AxiosRequestConfig) => data<T>(client.get(url, config)),
    post: <T>(url: string, body?: unknown, config?: AxiosRequestConfig) => data<T>(client.post(url, body, config)),
    put: <T>(url: string, body?: unknown, config?: AxiosRequestConfig) => data<T>(client.put(url, body, config)),
    patch: <T>(url: string, body?: unknown, config?: AxiosRequestConfig) => data<T>(client.patch(url, body, config)),
    delete: <T>(url: string, config?: AxiosRequestConfig) => data<T>(client.delete(url, config)),
  }
}

export const apiClient = createApiClient('/api/v1')
export const apiClientV2 = createApiClient('/api/v2')
