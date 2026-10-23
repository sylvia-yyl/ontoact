import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { apiClientV2, formatApiError } from '@/api/client'
import AutobindDialog from './AutobindDialog'
import { appsUrl } from './runtime'
import type { AppDefinition, AppRecord } from './spec'

/** Apps of the current ontology (picked in the top bar): open one, or generate one from an object type. */
export default function WorkshopListPage() {
  const [params] = useSearchParams()
  const ontologyId = params.get('ontology') ?? ''
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [generating, setGenerating] = useState(false)
  const apps = useQuery({ queryKey: ['workshop-apps', ontologyId], enabled: !!ontologyId, queryFn: () => apiClientV2.get<{ apps: Array<{ id: string; name: string; head_version: number; updated_at: string }> }>(appsUrl(ontologyId)) })
  const create = useMutation({ mutationFn: (body: { name: string; definition: AppDefinition }) => apiClientV2.post<AppRecord>(appsUrl(ontologyId), body),
    onSuccess: row => navigate(`/apps/workshop/${row.id}?ontology=${ontologyId}`) })
  return <div className="wb-page max-w-[1000px]" data-testid="workshop-list">
    <div className="wb-page-header"><div><p className="wb-eyebrow">Apps</p><h1 className="wb-page-title mt-2">Apps</h1>
      <p className="wb-page-subtitle">Operational apps built from standard widgets over ontology data. Generate a dashboard from any object type.</p></div></div>
    {!ontologyId && <p className="mt-6 text-sm text-slate-500">Select an ontology at the top of the page.</p>}
    {ontologyId && <>
      <ul className="mt-6 grid gap-3 sm:grid-cols-2" aria-label="Apps">{apps.data?.apps.map(row => <li key={row.id} className="wb-surface flex items-center gap-3 p-4">
        <span className="flex-1"><span className="block font-medium">{row.name}</span><span className="text-xs text-slate-500">v{row.head_version} · {row.updated_at.slice(0, 16).replace('T', ' ')}</span></span>
        <Link className="wb-button-primary" to={`/apps/workshop/${row.id}?ontology=${ontologyId}`}>Open</Link></li>)}</ul>
      {apps.data && !apps.data.apps.length && <p className="mt-4 text-sm text-slate-500">This ontology has no apps yet.</p>}
      <div className="mt-6 flex flex-wrap gap-2"><input className="wb-input w-72" placeholder="Name (optional)" aria-label="New app name" value={name} onChange={event => setName(event.target.value)} />
        <button className="wb-button-primary" onClick={() => setGenerating(true)}>Generate from object type…</button></div>
      {create.error && <p role="alert" className="mt-2 text-sm text-rose-700">{formatApiError(create.error)}</p>}
      {generating && <AutobindDialog ontologyId={ontologyId} prefix="auto_" applyLabel="Generate app" onClose={() => setGenerating(false)}
        onApply={(picked, result) => { setGenerating(false); create.mutate({ name: name.trim() || result.plan.page_title,
          definition: { schema: 'workshop-app/v1', data_sources: picked.data_sources, variables: [], pages: [picked.page], settings: { time_range: 'all', refresh_minutes: 0 } } }) }} />}
    </>}
  </div>
}
