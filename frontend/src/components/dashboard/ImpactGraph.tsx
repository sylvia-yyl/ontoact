import { useEffect, useMemo, useRef } from 'react'
import cytoscape from 'cytoscape'
import { plainId } from './binding'

export type ImpactNode = { id: string; kind: string; label: string; change?: 'better' | 'worse' | 'more' | 'less' | 'action' }
export type ImpactEdge = { source: string; target: string; kind: string }
export type Impact = {
  nodes: ImpactNode[]
  edges: ImpactEdge[]
  summary?: { orders_changed?: number; orders_better?: number; orders_worse?: number; product_lines?: number; supply_moved?: number; objects?: number }
  complete?: boolean
}

const COLUMN = 190        // between supply, part levels and the order blocks
const ORDER_COLUMNS = 12  // orders per row inside a product line block
const CELL = 16
const BLOCK_GAP = 34

type Element = { data: Record<string, string>; classes?: string; position?: { x: number; y: number } }

/**
 * Left to right: supply, parts (deepest first), assemblies, then one block of
 * orders per product line.  Orders connect to their line block, not one edge
 * each, so a few hundred orders stay readable.
 */
function build(impact: Impact): Element[] {
  const byId = new Map(impact.nodes.map(node => [node.id, node]))
  const depth = new Map<string, number>()
  const children = new Map<string, string[]>()
  const orderLine = new Map<string, string>()
  for (const edge of impact.edges) {
    if (edge.kind === 'REQUIRES') children.set(edge.source, [...(children.get(edge.source) ?? []), edge.target])
    if (edge.kind === 'ORDERS') depth.set(edge.target, 0)
    if (edge.kind === 'FOR_PRODUCT_LINE') orderLine.set(edge.source, edge.target)
  }
  const queue = [...depth.keys()]
  while (queue.length) {
    const id = queue.shift()!
    for (const child of children.get(id) ?? []) {
      if ((depth.get(child) ?? -1) < depth.get(id)! + 1) { depth.set(child, depth.get(id)! + 1); queue.push(child) }
    }
  }
  const deepest = Math.max(0, ...depth.values())

  // Order blocks, one per line, stacked; their total height sets the canvas height.
  const blocks = new Map<string, ImpactNode[]>()
  for (const node of impact.nodes) {
    if (node.kind !== 'CustomerOrder') continue
    const line = orderLine.get(node.id) ?? 'other'
    blocks.set(line, [...(blocks.get(line) ?? []), node])
  }
  const positions = new Map<string, { x: number; y: number }>()
  const blockX = (deepest + 2) * COLUMN
  let y = 0
  for (const [line, orders] of [...blocks].sort(([a], [b]) => a.localeCompare(b))) {
    orders.sort((a, b) => a.label.localeCompare(b.label))
    const rows = Math.ceil(orders.length / ORDER_COLUMNS)
    if (byId.has(line)) positions.set(line, { x: blockX, y: y + ((rows - 1) * CELL) / 2 })
    orders.forEach((order, index) => positions.set(order.id, { x: blockX + 40 + (index % ORDER_COLUMNS) * CELL, y: y + Math.floor(index / ORDER_COLUMNS) * CELL }))
    y += rows * CELL + BLOCK_GAP
  }
  const height = Math.max(y - BLOCK_GAP, 200)

  // Supply, parts and other nodes spread over the same height, one column each.
  const columns = new Map<number, ImpactNode[]>()
  for (const node of impact.nodes) {
    if (positions.has(node.id)) continue
    const column = node.kind === 'Supply' ? 0 : node.kind === 'Item' ? 1 + deepest - (depth.get(node.id) ?? deepest)
      : node.kind === 'CustomerOrder' ? deepest + 2 : deepest + 3
    columns.set(column, [...(columns.get(column) ?? []), node])
  }
  for (const [column, nodes] of columns) {
    nodes.sort((a, b) => a.label.localeCompare(b.label))
    const x = column > deepest + 1 ? blockX + 40 + ORDER_COLUMNS * CELL + 60 : column * COLUMN
    nodes.forEach((node, index) => positions.set(node.id, { x, y: ((index + 0.5) * height) / nodes.length }))
  }

  const labeled = (node: ImpactNode) => node.kind !== 'CustomerOrder' && node.kind !== 'Supply' ? node.label : node.change === 'action' ? node.label : ''
  const elements: Element[] = impact.nodes.map(node => ({ data: { id: node.id, label: plainId(labeled(node)) }, classes: [node.kind, node.change ?? ''].join(' '), position: positions.get(node.id) }))
  const seen = new Set<string>()
  impact.edges.forEach(edge => {
    // An order is drawn inside its line block: link its assembly to the line once instead.
    const [source, target] = edge.kind === 'ORDERS' ? [edge.target, orderLine.get(edge.source)] : edge.kind === 'FOR_PRODUCT_LINE' ? [undefined, undefined] : [edge.source, edge.target]
    if (!source || !target || !byId.has(source) || !byId.has(target)) return
    const key = `${source}>${target}`
    if (seen.has(key)) return
    seen.add(key)
    elements.push({ data: { id: `e${seen.size}`, source, target }, classes: edge.kind })
  })
  return elements
}

export default function ImpactGraph({ impact }: { impact: Impact }) {
  const host = useRef<HTMLDivElement | null>(null)
  const elements = useMemo(() => build(impact), [impact])
  useEffect(() => {
    if (!host.current) return
    const instance = cytoscape({
      container: host.current,
      elements,
      style: [
        { selector: 'node', style: { width: 10, height: 10, 'background-color': '#cbd5e1', label: 'data(label)', 'font-size': 11, color: '#334155',
          'text-valign': 'center', 'text-halign': 'left', 'text-margin-x': -5 } },
        { selector: 'node.CustomerOrder', style: { shape: 'round-rectangle', width: 11, height: 11 } },
        { selector: 'node.Item', style: { shape: 'round-rectangle', width: 12, height: 12, 'background-color': '#e2e8f0', 'border-width': 1, 'border-color': '#94a3b8' } },
        { selector: 'node.ProductLine, node.Resource', style: { shape: 'round-rectangle', width: 14, height: 14, 'background-color': '#1e3a8a', 'font-size': 12, 'font-weight': 600, color: '#0f172a' } },
        { selector: 'node.Supply', style: { shape: 'rectangle', width: 8, height: 8 } },
        { selector: 'node.better', style: { 'background-color': '#2563eb' } },
        { selector: 'node.worse', style: { 'background-color': '#0f172a' } },
        { selector: 'node.more', style: { 'background-color': '#60a5fa' } },
        { selector: 'node.less', style: { 'background-color': '#475569' } },
        { selector: 'node.action', style: { 'border-width': 3, 'border-color': '#2563eb', 'background-color': '#ffffff', width: 14, height: 14, 'font-weight': 600, color: '#1d4ed8' } },
        { selector: 'edge', style: { width: 0.8, 'line-color': '#cbd5e1', opacity: 0.8, 'curve-style': 'straight' } },
        { selector: 'edge.ORDERS', style: { width: 1.5, 'line-color': '#93c5fd' } },
        { selector: 'edge.MOVED_TO', style: { width: 0.5, opacity: 0.4 } },
      ],
      layout: { name: 'preset', padding: 24, animate: false },
      minZoom: 0.05,
      maxZoom: 3,
    })
    instance.fit(undefined, 24)
    return () => instance.destroy()
  }, [elements])

  const summary = impact.summary ?? {}
  const facts: Array<[string, number | undefined]> = [
    ['orders improve', summary.orders_better], ['orders slip', summary.orders_worse], ['product lines', summary.product_lines],
    ['supply sources reassigned', summary.supply_moved], ['objects touched', summary.objects],
  ]
  return (
    <div className="flex h-full flex-col gap-2" data-testid="impact-graph">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        {facts.filter(([, value]) => value !== undefined).map(([label, value]) =>
          <span key={label} className="text-xs text-slate-500"><strong className="text-sm tabular-nums text-slate-900">{value}</strong> {label}</span>)}
        {impact.complete === false ? <span className="text-xs text-slate-500">Largest objects shown</span> : null}
      </div>
      <div ref={host} className="min-h-0 flex-1 rounded border border-slate-200 bg-white" />
      <div className="flex flex-wrap gap-x-4 text-[11px] text-slate-500">
        <Legend color="#2563eb" label="Order improves" /><Legend color="#0f172a" label="Order slips" />
        <Legend color="#60a5fa" label="Supply used more" /><Legend color="#475569" label="Supply used less" />
        <Legend color="#ffffff" border="#2563eb" label="Changed by the action" />
      </div>
    </div>
  )
}

function Legend({ color, border, label }: { color: string; border?: string; label: string }) {
  return <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: color, border: `2px solid ${border ?? color}` }} />{label}</span>
}
