import { useEffect, useMemo, useRef, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import cytoscape from 'cytoscape'
import { ChevronRight } from 'lucide-react'
import { apiClientV2, formatApiError } from '@/api/client'
import { ontologyApi } from '@/api/ontologies'
import { plain } from '@/pages/what-if/decisionPackage'

type Property = { api_name: string; data_type: string }
type ObjectType = { api_name: string; properties: Property[]; count: number }
type LinkType = { api_name: string; source_type: string; target_type: string; count: number }
type Summary = { types: ObjectType[]; links: LinkType[] }
type ObjectRecord = { object_id: string; object_type: string; properties: Record<string, unknown> }
type Step = { type: string; id: string }
type Neighbor = { link: LinkType; direction: 'out' | 'in'; otherType: string }

/** "CustomerOrder" -> "Customer Order", "BOMLine" -> "BOM Line". */
const typeLabel = (name: string) => name.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
/** "IN_PRODUCT_LINE" -> "in product line"; snake_case properties the same way. */
const words = (name: string) => name.replace(/_/g, ' ').toLowerCase()
const objectName = (row: ObjectRecord) => String(row.properties.name ?? row.properties.code ?? plain(row.object_id))

const SAMPLE_SIZE = 25
const NEIGHBOR_PAGE = 20

function load(ontologyId: string, expression: unknown, pageSize: number) {
  return apiClientV2.post<{ objects: ObjectRecord[] }>(`/ontologies/${ontologyId}/object-query/load`,
    { expression, read: { page_size: pageSize }, context: { ontology_id: ontologyId } })
}

/** The ontology at a glance: object types and links with live counts, sample objects, and drill-down along links. */
export default function OntologyOverviewPage() {
  const [params] = useSearchParams()
  const ontologyId = params.get('ontology') ?? ''
  if (!ontologyId) return <div className="wb-page"><p className="text-sm text-slate-500">Select an ontology at the top of the page.</p></div>
  // Keyed by ontology so a switch starts from a clean selection.
  return <Overview key={ontologyId} ontologyId={ontologyId} />
}

function Overview({ ontologyId }: { ontologyId: string }) {
  const ontology = useQuery({ queryKey: ['ontology', ontologyId], enabled: !!ontologyId, queryFn: () => ontologyApi.get(ontologyId) })
  const summary = useQuery({ queryKey: ['ontology-summary', ontologyId], enabled: !!ontologyId,
    queryFn: () => apiClientV2.get<Summary>(`/ontologies/${ontologyId}/object-query/summary`) })
  const [selectedType, setSelectedType] = useState<string | null>(null)
  const [trail, setTrail] = useState<Step[]>([])
  const types = useMemo(() => summary.data?.types ?? [], [summary.data])
  const links = useMemo(() => summary.data?.links ?? [], [summary.data])
  // Default to the most connected type, the natural starting point for exploring.
  const hub = useMemo(() => [...types].sort((a, b) => degree(b.api_name, links) - degree(a.api_name, links))[0]?.api_name ?? null, [types, links])
  const activeType = selectedType ?? hub
  const totals = { objects: types.reduce((sum, row) => sum + row.count, 0), links: links.reduce((sum, row) => sum + row.count, 0) }

  const chooseType = (name: string) => { setSelectedType(name); setTrail([]) }
  const openObject = (step: Step, append: boolean) => { setSelectedType(step.type); setTrail(current => append ? [...current, step] : [step]) }

  return <div className="wb-page" data-testid="ontology-overview">
    <div className="wb-page-header"><div>
      <p className="wb-eyebrow">Ontology</p>
      <h1 className="wb-page-title mt-2">{ontology.data?.name ?? 'Ontology'}</h1>
      {ontology.data?.description && <p className="wb-page-subtitle">{ontology.data.description}</p>}
    </div></div>
    {summary.error && <p role="alert" className="mt-4 text-sm text-red-700">{formatApiError(summary.error)}</p>}
    {summary.data && <>
      <dl className="mt-5 grid max-w-xl grid-cols-3 gap-3" aria-label="Ontology size">
        {[['Object types', types.length], ['Objects', totals.objects], ['Links', totals.links]].map(([label, value]) =>
          <div key={label} className="wb-surface px-4 py-3"><dt className="text-xs text-slate-500">{label}</dt><dd className="text-2xl font-semibold tabular-nums text-slate-900">{Number(value).toLocaleString()}</dd></div>)}
      </dl>
      <div className="mt-5 grid gap-4">
        <section className="wb-surface overflow-hidden">
          <header className="border-b px-4 py-2.5 text-sm font-medium text-slate-700">Object types and links</header>
          <TypeGraph types={types} links={links} selected={activeType} onSelect={chooseType} />
        </section>
        <section className="wb-surface min-w-0 overflow-hidden">
          {trail.length > 0
            ? <ObjectDetail ontologyId={ontologyId} trail={trail} types={types} links={links} onOpen={openObject} onBack={index => setTrail(current => current.slice(0, index + 1))} onType={chooseType} />
            : activeType && <TypeDetail ontologyId={ontologyId} type={types.find(row => row.api_name === activeType)!} links={links} onOpen={step => openObject(step, false)} onType={chooseType} />}
        </section>
      </div>
    </>}
  </div>
}

function degree(name: string, links: LinkType[]) {
  return links.filter(link => link.source_type === name || link.target_type === name).length
}

/** Hub first, then the rest in an order that keeps types linked to each other next to each other on the ring. */
function ringOrder(types: ObjectType[], links: LinkType[]): string[] {
  const names = [...types].sort((a, b) => degree(b.api_name, links) - degree(a.api_name, links) || a.api_name.localeCompare(b.api_name)).map(row => row.api_name)
  const [hub, ...rest] = names
  if (!hub) return []
  // Links that do not touch the hub decide who should sit next to whom.
  const near = new Map(rest.map(name => [name, new Set<string>()]))
  for (const link of links) {
    if (link.source_type === hub || link.target_type === hub || link.source_type === link.target_type) continue
    near.get(link.source_type)?.add(link.target_type)
    near.get(link.target_type)?.add(link.source_type)
  }
  const ring: string[] = []
  const left = new Set(rest)
  while (left.size) {
    // Start each chain at an end (fewest neighbours), then walk to an unplaced neighbour.
    let current: string | undefined = [...left].sort((a, b) => near.get(a)!.size - near.get(b)!.size || rest.indexOf(a) - rest.indexOf(b))
      .find(name => near.get(name)!.size > 0) ?? [...left][0]
    while (current) {
      ring.push(current)
      left.delete(current)
      current = [...near.get(current)!].find(name => left.has(name))
    }
  }
  return [hub, ...ring]
}

/** Position of the index-th type in ringOrder: the hub at the centre, the rest clockwise from the top. */
function ringPosition(index: number, count: number) {
  if (index === 0) return { x: 0, y: 0 }
  const others = count - 1
  const radius = Math.max(260, (others * 230) / (2 * Math.PI))
  const angle = -Math.PI / 2 + ((index - 1) * 2 * Math.PI) / others
  return { x: Math.round(radius * 1.35 * Math.cos(angle)), y: Math.round(radius * Math.sin(angle)) }
}

function TypeGraph({ types, links, selected, onSelect }: { types: ObjectType[]; links: LinkType[]; selected: string | null; onSelect: (name: string) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const cy = useRef<cytoscape.Core | null>(null)
  const select = useRef(onSelect)
  useEffect(() => { select.current = onSelect }, [onSelect])
  useEffect(() => {
    if (!ref.current) return
    const instance = cytoscape({
      container: ref.current,
      elements: [
        ...ringOrder(types, links).map((name, index) => {
          const row = types.find(item => item.api_name === name)!
          return { data: { id: name, label: `${typeLabel(name)}\n${row.count.toLocaleString()}` }, position: ringPosition(index, types.length) }
        }),
        ...links.map(link => ({ data: { id: `${link.source_type}|${link.api_name}|${link.target_type}`, source: link.source_type, target: link.target_type, label: words(link.api_name) } })),
      ],
      style: [
        { selector: 'node', style: { shape: 'round-rectangle', width: 200, height: 70, 'background-color': '#ffffff', 'border-width': 1.5, 'border-color': '#93c5fd',
          label: 'data(label)', 'text-wrap': 'wrap', 'text-valign': 'center', 'text-halign': 'center', 'font-size': 19, color: '#0f172a', 'font-family': 'Inter, system-ui, sans-serif' } },
        { selector: 'node.is-selected', style: { 'background-color': '#2563eb', 'border-color': '#1d4ed8', color: '#ffffff' } },
        { selector: 'edge', style: { width: 2, 'line-color': '#93c5fd', 'target-arrow-color': '#93c5fd', 'target-arrow-shape': 'triangle', 'curve-style': 'bezier',
          label: 'data(label)', 'font-size': 15, color: '#64748b', 'text-background-color': '#ffffff', 'text-background-opacity': 1, 'text-background-padding': '2px', 'text-rotation': 'autorotate' } },
        { selector: 'edge.is-adjacent', style: { 'line-color': '#2563eb', 'target-arrow-color': '#2563eb', color: '#1d4ed8', width: 3 } },
      ],
      // Hub in the middle, every other type evenly on one ring in ringOrder: the same picture on every visit.
      layout: { name: 'preset', padding: 24, animate: false },
      userZoomingEnabled: true, wheelSensitivity: 0.2,
    })
    instance.on('tap', 'node', event => select.current(event.target.id()))
    cy.current = instance
    return () => { instance.destroy(); cy.current = null }
  }, [types, links])
  useEffect(() => {
    const instance = cy.current
    if (!instance) return
    instance.elements().removeClass('is-selected is-adjacent')
    if (!selected) return
    const node = instance.getElementById(selected)
    node.addClass('is-selected')
    node.connectedEdges().addClass('is-adjacent')
  }, [selected, types, links])
  return <div ref={ref} className="h-[640px] w-full bg-[var(--surface-canvas)]" role="img" aria-label={`Ontology graph: ${types.length} object types, ${links.length} link types`} data-testid="type-graph" />
}

function neighborsOf(type: string, links: LinkType[]): Neighbor[] {
  return links.flatMap(link => [
    ...(link.source_type === type ? [{ link, direction: 'out' as const, otherType: link.target_type }] : []),
    ...(link.target_type === type ? [{ link, direction: 'in' as const, otherType: link.source_type }] : []),
  ])
}

function linkPhrase(neighbor: Neighbor) {
  return neighbor.direction === 'out' ? `${words(neighbor.link.api_name)} → ${typeLabel(neighbor.otherType)}` : `${typeLabel(neighbor.otherType)} ← ${words(neighbor.link.api_name)}`
}

function TypeDetail({ ontologyId, type, links, onOpen, onType }: { ontologyId: string; type: ObjectType; links: LinkType[]; onOpen: (step: Step) => void; onType: (name: string) => void }) {
  const sample = useQuery({ queryKey: ['type-sample', ontologyId, type.api_name], enabled: type.count > 0,
    queryFn: () => load(ontologyId, { kind: 'base', type_ref: { api_name: type.api_name } }, SAMPLE_SIZE) })
  const columns = type.properties.map(row => row.api_name).filter(name => name !== '_instance_id').slice(0, 5)
  return <div data-testid="type-detail">
    <header className="border-b px-4 py-3">
      <h2 className="text-base font-semibold text-slate-900">{typeLabel(type.api_name)}</h2>
      <p className="text-xs text-slate-500">{type.count.toLocaleString()} objects · {type.properties.length - 1} properties</p>
    </header>
    <div className="space-y-4 p-4">
      <div><h3 className="wb-eyebrow">Links</h3>
        <ul className="mt-1.5 flex flex-wrap gap-1.5">{neighborsOf(type.api_name, links).map(row => <li key={`${row.link.api_name}-${row.direction}-${row.otherType}`}>
          <button className="rounded border border-blue-200 bg-blue-50 px-2 py-0.5 text-xs text-blue-800 hover:border-blue-400" onClick={() => onType(row.otherType)}>{linkPhrase(row)} · {row.link.count.toLocaleString()}</button></li>)}</ul></div>
      <div><h3 className="wb-eyebrow">Sample objects</h3>
        {sample.error && <p role="alert" className="mt-2 text-sm text-red-700">{formatApiError(sample.error)}</p>}
        {type.count === 0 && <p className="mt-2 text-sm text-slate-500">No objects of this type yet.</p>}
        {sample.data && <div className="mt-1.5 max-h-[360px] overflow-auto rounded border"><table className="w-full text-left text-xs" aria-label={`${typeLabel(type.api_name)} sample`}>
          <thead className="sticky top-0 bg-slate-50 text-slate-500"><tr>{columns.map(name => <th key={name} className="border-b px-2 py-1.5 font-medium">{words(name)}</th>)}</tr></thead>
          <tbody>{sample.data.objects.map(row => <tr key={row.object_id} className="cursor-pointer border-b hover:bg-blue-50" onClick={() => onOpen({ type: type.api_name, id: row.object_id })}>
            {columns.map(name => <td key={name} className="px-2 py-1.5">{display(row.properties[name])}</td>)}</tr>)}</tbody></table></div>}
        {sample.data && type.count > SAMPLE_SIZE && <p className="mt-1 text-[11px] text-slate-400">Showing {SAMPLE_SIZE} of {type.count.toLocaleString()}</p>}
      </div>
    </div>
  </div>
}

function display(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'number') return value.toLocaleString(undefined, { maximumFractionDigits: 2 })
  return plain(Array.isArray(value) ? value.join(', ') : String(value))
}

function ObjectDetail({ ontologyId, trail, types, links, onOpen, onBack, onType }: { ontologyId: string; trail: Step[]; types: ObjectType[]; links: LinkType[]; onOpen: (step: Step, append: boolean) => void; onBack: (index: number) => void; onType: (name: string) => void }) {
  const current = trail[trail.length - 1]
  const object = useQuery({ queryKey: ['object', ontologyId, current.type, current.id],
    queryFn: () => load(ontologyId, { kind: 'static', type_ref: { api_name: current.type }, object_ids: [current.id] }, 1) })
  const neighbors = neighborsOf(current.type, links).filter(row => row.link.count > 0)
  const linked = useQueries({ queries: neighbors.map(row => ({
    queryKey: ['linked', ontologyId, current.type, current.id, row.link.api_name, row.direction, row.otherType],
    queryFn: () => load(ontologyId, { kind: 'traverse', input: { kind: 'static', type_ref: { api_name: current.type }, object_ids: [current.id] },
      link: { api_name: row.link.api_name, direction: row.direction } }, NEIGHBOR_PAGE),
  })) })
  const record = object.data?.objects[0]
  const type = types.find(row => row.api_name === current.type)
  return <div data-testid="object-detail">
    <nav className="flex flex-wrap items-center gap-1 border-b px-4 py-2 text-xs text-slate-500" aria-label="Path">
      <button className="hover:text-blue-700" onClick={() => onType(trail[0].type)}>{typeLabel(trail[0].type)}</button>
      {trail.map((step, index) => <span key={`${step.type}-${step.id}-${index}`} className="flex items-center gap-1"><ChevronRight size={12} />
        <button className={index === trail.length - 1 ? 'font-medium text-slate-900' : 'hover:text-blue-700'} onClick={() => onBack(index)}>{plain(step.id)}</button></span>)}
    </nav>
    <div className="space-y-4 p-4">
      <header><p className="text-xs text-slate-500">{typeLabel(current.type)}</p><h2 className="text-base font-semibold text-slate-900">{record ? objectName(record) : plain(current.id)}</h2></header>
      {object.error && <p role="alert" className="text-sm text-red-700">{formatApiError(object.error)}</p>}
      {record && <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">{(type?.properties ?? []).filter(row => row.api_name !== '_instance_id').map(row =>
        <div key={row.api_name} className="flex justify-between gap-2 border-b border-slate-100 py-1"><dt className="text-slate-500">{words(row.api_name)}</dt><dd className="text-right font-medium text-slate-800">{display(record.properties[row.api_name])}</dd></div>)}</dl>}
      <div className="space-y-3">{neighbors.map((row, index) => { const result = linked[index]; const rows = result.data?.objects ?? []
        if (result.data && !rows.length) return null  // this object has no links of this kind
        return <div key={`${row.link.api_name}-${row.direction}-${row.otherType}`}>
          <h3 className="wb-eyebrow">{linkPhrase(row)}{result.data && ` · ${rows.length}${rows.length === NEIGHBOR_PAGE ? '+' : ''}`}</h3>
          {result.error && <p role="alert" className="text-xs text-red-700">{formatApiError(result.error)}</p>}
          <ul className="mt-1 flex flex-wrap gap-1.5">{rows.map(item => <li key={item.object_id}>
            <button className="rounded border border-slate-200 bg-white px-2 py-0.5 text-xs text-slate-700 hover:border-blue-400 hover:text-blue-800" onClick={() => onOpen({ type: item.object_type, id: item.object_id }, true)}>{objectName(item)}</button></li>)}</ul>
        </div> })}</div>
    </div>
  </div>
}
