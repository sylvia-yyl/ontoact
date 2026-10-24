import { LayoutDashboard, Network, SearchCode } from 'lucide-react'

export interface NavEntry {
  key: string
  label: string
  icon: React.ElementType
  hint?: string
  /** The page for the current ontology. */
  path: (ontologyId: string | null) => string
  /** Pathnames that count as this entry being active. */
  activeOn: RegExp
}

export const NAV_ENTRIES: NavEntry[] = [
  { key: 'ontology', label: 'Ontology', icon: Network, hint: 'Object types, links and objects',
    path: id => (id ? `/ontology?ontology=${id}` : '/ontology'), activeOn: /^\/ontology/ },
  { key: 'apps', label: 'Apps', icon: LayoutDashboard, hint: 'Dashboards and decision workspaces',
    path: id => (id ? `/apps/workshop?ontology=${id}` : '/apps/workshop'), activeOn: /^\/apps\/workshop/ },
  { key: 'queries', label: 'Queries', icon: SearchCode, hint: 'Reusable, versioned ontology queries',
    path: id => (id ? `/apps/queries?ontology=${id}` : '/apps/queries'), activeOn: /^\/apps\/queries/ },
]

/** The ontology a URL is about: ?ontology= or ?ontology_id=. */
export function ontologyIdFromUrl(search: string): string | null {
  const params = new URLSearchParams(search)
  return params.get('ontology') || params.get('ontology_id') || null
}

/** The URL to open when the current ontology changes on `pathname`; null when the page is not ontology-scoped. */
export function urlForOntologySwitch(pathname: string, search: string, nextId: string): string | null {
  // An open app or run belongs to the previous ontology, so go back to the list.
  if (pathname.startsWith('/apps/workshop')) return `/apps/workshop?ontology=${nextId}`
  const params = new URLSearchParams(search)
  if (params.has('ontology') || pathname.startsWith('/apps/queries') || pathname === '/ontology') {
    params.set('ontology', nextId)
    return `${pathname}?${params.toString()}`
  }
  return null
}

const STORAGE_KEY = 'ontoact_current_ontology'

export function readStoredOntology(): string | null {
  try { return localStorage.getItem(STORAGE_KEY) } catch { return null }
}

export function writeStoredOntology(id: string | null) {
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id)
    else localStorage.removeItem(STORAGE_KEY)
  } catch { /* storage blocked: the URL still carries the choice */ }
}
