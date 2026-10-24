import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, LogOut, Network } from 'lucide-react'
import { ontologyApi } from '@/api/ontologies'
import { useAuthStore } from '@/stores/authStore'
import { NAV_ENTRIES, ontologyIdFromUrl, readStoredOntology, urlForOntologySwitch, writeStoredOntology } from '@/components/navigation'

const LOCAL_SINGLE_USER = import.meta.env.VITE_AUTH_MODE === 'local_single_user'

export default function Layout({ children }: { children: React.ReactNode }) {
  const logout = useAuthStore(s => s.logout)
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)

  // Current ontology: the one the URL is about, else the last one chosen.
  const fromUrl = ontologyIdFromUrl(location.search)
  const [stored, setStored] = useState(readStoredOntology)
  if (fromUrl && fromUrl !== stored) setStored(fromUrl)
  useEffect(() => { writeStoredOntology(stored) }, [stored])
  const ontologies = useQuery({ queryKey: ['ontologies', 'switcher'], queryFn: () => ontologyApi.list({ page_size: 200 }) })
  const items = ontologies.data?.items ?? []
  const current = items.find(item => item.id === stored) ?? null
  const currentId = current?.id ?? (ontologies.data ? null : stored)

  // A section opened without an ontology in the URL (sign-in, the logo, a bookmark) uses the last one chosen.
  useEffect(() => {
    if (fromUrl || !currentId) return
    const entry = NAV_ENTRIES.find(row => location.pathname === row.path(null))
    if (entry) navigate(entry.path(currentId), { replace: true })
  }, [fromUrl, currentId, location.pathname, navigate])

  const switchOntology = (nextId: string) => {
    setStored(nextId || null)
    if (!nextId) return
    const next = urlForOntologySwitch(location.pathname, location.search, nextId)
    if (next) navigate(next)
  }

  return (
    <div className="min-h-screen bg-[var(--surface-canvas)]">
      <aside className={`fixed inset-y-0 left-0 z-30 flex flex-col bg-[var(--surface-sidebar)] text-white transition-[width] duration-200 ${collapsed ? 'w-[72px]' : 'w-[220px]'}`}>
        <div className={`flex h-[60px] shrink-0 items-center border-b border-white/10 ${collapsed ? 'justify-center px-3' : 'px-5'}`}>
          <Link to={NAV_ENTRIES[0].path(currentId)} className="flex min-w-0 items-center gap-3" aria-label="OntoAct home">
            <img src="/logo.svg" alt="" className="h-8 w-8 shrink-0" />
            {!collapsed && <span className="truncate text-[15px] font-semibold tracking-[.01em]">OntoAct</span>}
          </Link>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-3" aria-label="Main">
          <div className="space-y-px">
            {NAV_ENTRIES.map(entry => {
              const Icon = entry.icon
              const active = entry.activeOn.test(location.pathname)
              return (
                <Link key={entry.key} to={entry.path(currentId)} aria-current={active ? 'page' : undefined} title={collapsed ? entry.label : entry.hint}
                  className={`flex items-center gap-3 rounded-md px-3 py-1.5 text-[13px] transition-colors ${active ? 'bg-[var(--brand)] text-white' : 'text-slate-300 hover:bg-white/10 hover:text-white'}`}>
                  <Icon size={16} className="shrink-0" strokeWidth={1.8} />
                  {!collapsed && <span className="min-w-0 flex-1 truncate">{entry.label}</span>}
                </Link>
              )
            })}
          </div>
        </nav>

        <div className="shrink-0 border-t border-white/10 p-3">
          <button type="button" onClick={() => setCollapsed(value => !value)} className="flex w-full items-center justify-center rounded-lg py-1.5 text-slate-400 hover:bg-white/10 hover:text-white" aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>{collapsed ? <ChevronRight size={17} /> : <ChevronLeft size={17} />}</button>
          {!LOCAL_SINGLE_USER && <button type="button" onClick={() => { logout(); navigate('/login') }} className={`mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-400 hover:bg-white/10 hover:text-white ${collapsed ? 'justify-center' : ''}`}><LogOut size={15} />{!collapsed && 'Sign out'}</button>}
        </div>
      </aside>

      <main className={`min-h-screen min-w-0 transition-[padding] duration-200 ${collapsed ? 'pl-[72px]' : 'pl-[220px]'}`}>
        <header className="sticky top-0 z-20 flex h-[52px] items-center gap-3 border-b border-slate-200 bg-white/95 px-8 backdrop-blur xl:px-10" aria-label="Ontology">
          <Network size={16} className="shrink-0 text-slate-400" />
          <label htmlFor="current-ontology" className="shrink-0 text-xs text-slate-500">Ontology</label>
          <select id="current-ontology" value={currentId ?? ''} onChange={event => switchOntology(event.target.value)}
            className="min-w-0 max-w-[340px] flex-1 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm text-slate-800 focus:border-[var(--brand)] focus:outline-none">
            <option value="">Select an ontology…</option>
            {items.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          {current && <span className="hidden truncate text-xs text-slate-400 lg:inline">{current.entity_count} object types · {current.relation_count} link types</span>}
          {ontologies.error && <span role="alert" className="truncate text-xs text-red-700">Could not load ontologies</span>}
        </header>
        <div className="px-8 py-6 xl:px-10">{children}</div>
      </main>
    </div>
  )
}
