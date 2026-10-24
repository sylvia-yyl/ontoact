import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { apiClientV2, formatApiError } from '@/api/client'
import { pickWidgets, type AutobindResult } from './editorModel'
import { specOf, type DataSource, type Page } from './spec'

const ROLE: Record<string, string> = { time: 'Time', measure: 'Measure', flag: '0/1 flag', category: 'Category', key: 'Key', identifier: 'Identifier', other: 'Other' }
const MODES = [['rules', 'Rules (deterministic, instant)'], ['llm', 'AI model (better titles; may vary between runs)']] as const

/** One-click binding: pick an object type, preview the generated page, keep what you want. */
export default function AutobindDialog({ ontologyId, prefix, applyLabel, onApply, onClose }: {
  ontologyId: string; prefix: string; applyLabel: string; onApply: (picked: { data_sources: DataSource[]; page: Page }, result: AutobindResult) => void; onClose: () => void
}) {
  const catalog = useQuery({ queryKey: ['query-catalog', ontologyId], queryFn: () => apiClientV2.get<{ types: Array<{ api_name: string }> }>(`/ontologies/${ontologyId}/object-query/catalog`) })
  const [objectType, setObjectType] = useState('')
  const [mode, setMode] = useState<'rules' | 'llm'>('rules')
  const [keep, setKeep] = useState<Set<string>>(new Set())
  const generate = useMutation({
    mutationFn: () => apiClientV2.post<AutobindResult>(`/ontologies/${ontologyId}/workshop-apps:autobind`, { object_type: objectType, mode, prefix }, { timeout: 180000 }),
    onSuccess: result => setKeep(new Set(result.page.widgets.map(row => row.id))),
  })
  const result = generate.data
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40" role="dialog" aria-label="Generate app" data-testid="autobind-dialog">
    <div className="max-h-[90vh] w-[880px] max-w-[95vw] overflow-auto rounded bg-white p-5 shadow-xl">
      <h2 className="text-base font-semibold">Generate a page from an object type</h2>
      <p className="mt-1 text-xs text-slate-500">OntoAct profiles the type's fields, picks a role for each and configures data sources and widgets. Preview first, keep what you want, then generate.</p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <label className="text-xs text-slate-500">Object type<select className="wb-input mt-0.5 block w-56" aria-label="Object type" value={objectType} onChange={event => setObjectType(event.target.value)}>
          <option value="">Select…</option>{catalog.data?.types.map(row => <option key={row.api_name} value={row.api_name}>{row.api_name}</option>)}</select></label>
        <fieldset className="flex gap-3 text-xs" aria-label="Method">{MODES.map(([value, label]) => <label key={value} className="flex items-center gap-1">
          <input type="radio" name="autobind-mode" checked={mode === value} onChange={() => setMode(value)} />{label}</label>)}</fieldset>
        <button className="wb-button-primary" disabled={!objectType || generate.isPending} onClick={() => generate.mutate()}>{generate.isPending ? 'Generating…' : 'Preview'}</button>
      </div>
      {generate.error && <p role="alert" className="mt-3 text-sm text-rose-700">{formatApiError(generate.error)}</p>}
      {result && <div className="mt-4 grid gap-4 md:grid-cols-2">
        <section><h3 className="text-xs font-semibold text-slate-600">Fields ({result.profile.label} · {result.profile.count.toLocaleString()} objects)</h3>
          <table className="mt-1 w-full text-xs" data-testid="autobind-fields"><tbody>{result.profile.fields.map(field => <tr key={field.name} className="border-b">
            <td className="py-1 pr-2">{field.label}{field.label !== field.name && <span className="text-slate-400"> {field.name}</span>}</td>
            <td className="pr-2">{ROLE[field.role] ?? field.role}{field.dimension ? ` → ${field.dimension}` : ''}</td><td className="text-slate-400">{field.distinct} values</td></tr>)}</tbody></table></section>
        <section><h3 className="text-xs font-semibold text-slate-600">Will generate: {result.plan.page_title}{result.model && <span className="font-normal text-slate-400"> · {result.model}</span>}</h3>
          <ul className="mt-1 space-y-1 text-sm" data-testid="autobind-widgets">{result.page.widgets.map(widget => <li key={widget.id}><label className="flex items-center gap-2">
            <input type="checkbox" checked={keep.has(widget.id)} onChange={event => setKeep(current => { const next = new Set(current); if (event.target.checked) next.add(widget.id); else next.delete(widget.id); return next })} />
            <span className="rounded bg-slate-100 px-1.5 text-[11px] text-slate-600">{specOf(widget.type)?.label}</span>
            <span>{widget.title || (widget.type === 'kpi_strip' ? (widget.props.items as Array<{ label: string }>).map(row => row.label).join(' · ') : widget.id)}</span></label></li>)}</ul>
          {result.plan.reasoning && <p className="mt-2 rounded bg-blue-50 p-2 text-xs text-blue-900">Model notes: {result.plan.reasoning}</p>}
          {result.dropped.length > 0 && <div className="mt-2 rounded bg-blue-50 p-2 text-xs text-blue-900" data-testid="autobind-dropped"><p>These model choices did not fit the data and were dropped:</p><ul className="list-disc pl-4">{result.dropped.map(row => <li key={row}>{row}</li>)}</ul></div>}
        </section>
      </div>}
      <div className="mt-4 flex justify-end gap-2">
        <button className="wb-button-secondary" onClick={onClose}>Cancel</button>
        <button className="wb-button-primary" disabled={!result || keep.size === 0} onClick={() => result && onApply(pickWidgets(result, keep), result)}>{applyLabel}</button>
      </div>
    </div>
  </div>
}
