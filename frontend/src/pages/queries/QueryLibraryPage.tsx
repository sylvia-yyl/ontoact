import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { apiClientV2, formatApiError } from '@/api/client'
import { DataTable } from '@/components/dashboard/widgets'
import { formatCell, type Row } from '@/components/dashboard/binding'
import { TIME_RANGES, type QuerySummary, type TimeRange } from '@/pages/workshop/spec'

type Detail = QuerySummary & { versions: Array<{ version: string; change_note: string; created_at: string }>; references: Array<{ app_id: string; app_name: string; version: string }> }
type RunResult = { version: string; outputs: Record<string, unknown> & { count: number } }

const SHAPE = { single: 'Single row', '2d': 'Grouped by one field', '3d': 'Grouped by two fields', table: 'Detail table' }
const ROLE: Record<string, string> = { dimension: 'Dimension', name: 'Name', category: 'Category', metric: 'Metric', measure: 'Measure', time: 'Time', latitude: 'Latitude', longitude: 'Longitude', identifier: 'Identifier' }

/** The ontology's shared queries: what each returns, its versions, who uses it, and a trial run. */
export default function QueryLibraryPage() {
  const [params] = useSearchParams()
  const ontologyId = params.get('ontology') ?? ''
  const [selected, setSelected] = useState('')
  const list = useQuery({ queryKey: ['queries', ontologyId], enabled: !!ontologyId, queryFn: () => apiClientV2.get<{ queries: QuerySummary[] }>(`/ontologies/${ontologyId}/queries`) })
  const current = selected || list.data?.queries[0]?.api_name || ''
  return <div className="wb-page max-w-[1200px]" data-testid="query-library">
    <div className="wb-page-header"><div><p className="wb-eyebrow">Ontology</p><h1 className="wb-page-title mt-2">Queries</h1>
      <p className="wb-page-subtitle">Define a query once and reuse it everywhere: app pages, the HTTP API and external agents all read the same definition.</p></div></div>
    {!ontologyId && <p className="mt-6 text-sm text-slate-500">Select an ontology at the top of the page.</p>}
    {list.error && <p role="alert" className="mt-4 text-sm text-rose-700">{formatApiError(list.error)}</p>}
    {list.data && !list.data.queries.length && <p className="mt-6 text-sm text-slate-500">This ontology has no queries yet.</p>}
    {!!list.data?.queries.length && <div className="mt-6 grid gap-4 md:grid-cols-[320px_minmax(0,1fr)]">
      <ul className="space-y-2" aria-label="Queries">{list.data.queries.map(row => <li key={row.api_name}>
        <button onClick={() => setSelected(row.api_name)} className={`w-full rounded border p-3 text-left ${row.api_name === current ? 'border-blue-500 bg-blue-50' : 'bg-white hover:border-slate-400'}`}>
          <span className="block font-medium">{row.name}</span>
          <span className="block text-xs text-slate-500">{row.api_name} · v{row.latest_version} · {SHAPE[row.output_schema.shape]} · used by {row.references ?? 0} apps</span></button></li>)}</ul>
      {current && <QueryDetail ontologyId={ontologyId} apiName={current} />}
    </div>}
  </div>
}

function QueryDetail({ ontologyId, apiName }: { ontologyId: string; apiName: string }) {
  const detail = useQuery({ queryKey: ['query', ontologyId, apiName], queryFn: () => apiClientV2.get<Detail>(`/ontologies/${ontologyId}/queries/${apiName}`) })
  const [range, setRange] = useState<TimeRange>('all')
  const [values, setValues] = useState<Record<string, string>>({})
  const run = useMutation({ mutationFn: () => apiClientV2.post<RunResult>(`/ontologies/${ontologyId}/queries/${apiName}:run`,
    { range, limit: 50, params: Object.fromEntries(Object.entries(values).filter(([, value]) => value)) }, { timeout: 120000 }) })
  const q = detail.data
  if (detail.error) return <p role="alert" className="text-sm text-rose-700">{formatApiError(detail.error)}</p>
  if (!q) return <p className="text-sm text-slate-500">Loading…</p>
  const rows = (run.data?.outputs[q.output_schema.path] as Row[] | undefined) ?? []
  return <section className="wb-surface space-y-4 p-4" data-testid="query-detail">
    <div><h2 className="text-lg font-semibold">{q.name}</h2><p className="text-xs text-slate-500">{q.api_name} · reads {q.object_type ?? 'alerts'} · {SHAPE[q.output_schema.shape]}</p>
      {q.description && <p className="mt-1 text-sm">{q.description}</p>}</div>
    <div><h3 className="text-xs font-semibold text-slate-600">Columns</h3>
      <ul className="mt-1 flex flex-wrap gap-1.5 text-xs">{q.output_schema.columns.map(col => <li key={col.name} className="rounded border px-2 py-0.5">{col.label}<span className="text-slate-400"> · {ROLE[col.role] ?? col.role}</span></li>)}</ul></div>
    <div className="grid gap-4 md:grid-cols-2">
      <div><h3 className="text-xs font-semibold text-slate-600">Versions</h3><ul className="mt-1 space-y-0.5 text-xs">{q.versions.map(v => <li key={v.version}><strong>v{v.version}</strong> · {v.created_at.slice(0, 16).replace('T', ' ')} {v.change_note && `· ${v.change_note}`}</li>)}</ul>
        <p className="mt-1 text-[11px] text-slate-500">Apps follow the latest version within a major version. Removing a column, changing a type or adding a required parameter starts a new major version, so existing apps are not affected.</p></div>
      <div><h3 className="text-xs font-semibold text-slate-600">Used by</h3>
        {q.references.length ? <ul className="mt-1 space-y-0.5 text-xs">{q.references.map(r => <li key={r.app_id + r.version}><Link className="text-blue-700 hover:underline" to={`/apps/workshop/${r.app_id}?ontology=${ontologyId}`}>{r.app_name}</Link> · follows {r.version || 'latest'}</li>)}</ul>
          : <p className="mt-1 text-xs text-slate-500">No apps use this query yet.</p>}</div>
    </div>
    <div className="space-y-2 border-t pt-3"><h3 className="text-xs font-semibold text-slate-600">Try it (with your permissions)</h3>
      <div className="flex flex-wrap items-end gap-2 text-xs">
        <label>Time<select className="wb-input ml-1 py-1 text-xs" aria-label="Time range" value={range} onChange={event => setRange(event.target.value as TimeRange)}>{TIME_RANGES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        {q.params.map(param => <label key={param.name}>{param.label || param.field}<input className="wb-input ml-1 w-28 py-1 text-xs" aria-label={`Parameter ${param.name}`} placeholder={param.required ? 'Required' : 'Optional'}
          value={values[param.name] ?? ''} onChange={event => setValues(current => ({ ...current, [param.name]: event.target.value }))} /></label>)}
        <button className="wb-button-primary" disabled={run.isPending} onClick={() => run.mutate()}>{run.isPending ? 'Running…' : 'Run'}</button></div>
      {run.error && <p role="alert" className="text-xs text-rose-700">{formatApiError(run.error)}</p>}
      {run.data && <><p className="text-xs text-slate-500">v{run.data.version} · {run.data.outputs.count} rows (showing up to 50)</p>
        <div className="max-h-80 overflow-auto rounded border" data-testid="query-run-result"><DataTable label="Result" rows={rows.slice(0, 50)} rowKey={row => JSON.stringify(row)}
          columns={q.output_schema.columns.map(col => ({ label: col.label, value: (row: Row) => row[col.name], format: col.type === 'timestamp' ? 'date' : col.role === 'metric' || col.role === 'measure' ? 'number' : 'text' }))} /></div>
        <p className="text-[11px] text-slate-400">API: POST /api/v2/ontologies/{ontologyId}/queries/{q.api_name}:run · {formatCell(run.data.outputs.count, 'number')} rows</p></>}
    </div>
  </section>
}
