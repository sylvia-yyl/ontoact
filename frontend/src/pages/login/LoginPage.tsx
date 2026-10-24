import { useForm } from 'react-hook-form'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { authApi } from '@/api/auth'
import { getApiErrorStatus } from '@/api/client'
import { useState } from 'react'

export default function LoginPage() {
  const { register, handleSubmit } = useForm<{ username: string; password: string }>()
  const setAuth = useAuthStore(s => s.setAuth)
  const logout = useAuthStore(s => s.logout)
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const onSubmit = async (data: { username: string; password: string }) => {
    setLoading(true)
    setError('')
    try {
      const res = await authApi.login(data.username, data.password)
      localStorage.setItem('token', res.access_token)
      const profile = await authApi.profile()
      setAuth(profile, res.access_token)
      navigate('/ontology')
    } catch (e: unknown) {
      logout()
      const status = getApiErrorStatus(e)
      setError(status === 401 ? 'Incorrect username or password.'
        : status === 429 ? 'Too many attempts. Try again in a minute.'
        : status !== undefined ? 'Sign-in is unavailable right now. Try again shortly.'
        : 'Cannot reach the server. Check your connection.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--surface-canvas)]">
      <div className="w-full max-w-sm bg-white rounded-xl border border-slate-200 shadow-sm p-8">
        <div className="mb-6 flex items-center gap-3">
          <img src="/logo.svg" alt="" className="h-9 w-9" />
          <div>
            <h1 className="text-xl font-semibold text-slate-900">OntoAct</h1>
            <p className="text-slate-500 text-sm">From ontology to reviewed actions</p>
          </div>
        </div>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label htmlFor="username" className="block text-sm font-medium mb-1">Username</label>
            <input id="username" autoComplete="username" {...register('username', { required: true })} className="wb-input w-full" />
          </div>
          <div>
            <label htmlFor="password" className="block text-sm font-medium mb-1">Password</label>
            <input id="password" type="password" autoComplete="current-password" {...register('password', { required: true })} className="wb-input w-full" />
          </div>
          {error && <p role="alert" className="text-red-600 text-sm">{error}</p>}
          <button type="submit" disabled={loading} className="wb-button-primary w-full disabled:opacity-50">
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
