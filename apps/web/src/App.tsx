import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Aperture, ArrowRight, CalendarDays, CircleAlert, Clapperboard, Command, LayoutGrid, LibraryBig, LoaderCircle, LogOut, Menu, RefreshCw, X } from 'lucide-react'
import { api, ApiError } from './api'
import { Button, ErrorNotice } from './components/Common'
import { ThemeControl } from './components/ThemeControl'
import { Board } from './features/Board'
import { Calendar } from './features/Calendar'
import { Library } from './features/Library'
import { Studio } from './features/Studio'
import type { AuthSession, BatchSummary, Bootstrap, SourceAsset } from './types'
import { errorMessage } from './utils'

type Page = 'studio' | 'board' | 'calendar' | 'library'

export default function App() {
  const auth = useQuery({ queryKey: ['auth'], queryFn: api.me, retry: false })
  if (auth.isPending) return <div className="app-loading"><Aperture size={30} /><LoaderCircle size={21} className="spin" /><span>Opening your workspace…</span></div>
  if (auth.isError && auth.error instanceof ApiError && auth.error.status === 401) return <Login />
  if (auth.isError) return <div className="connection-screen"><Aperture size={34} /><span className="eyebrow">CONNECTION REQUIRED</span><h1>The studio is offline.</h1><p>{errorMessage(auth.error)}</p><Button onClick={() => void auth.refetch()}><RefreshCw size={16} /> Check connection</Button></div>
  return <Workspace session={auth.data} />
}

function Login() {
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const login = useMutation({ mutationFn: () => api.login(email.trim(), password), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ['auth'] }) } })
  return <main className="login-screen">
    <div className="login-art" aria-hidden="true"><div className="login-mark"><Aperture size={38} /></div><div className="login-art-bottom"><span>01 / THE EDITORIAL WORKSPACE</span><h1>Every story.<br /><em>A source.</em></h1><p>One production desk for source evidence, editorial decisions and the final handoff.</p></div><div className="login-production"><div><span className="signal-dot" /> SOURCE / TRANSCRIPT</div><svg viewBox="0 0 560 90" fill="none"><path d="M0 45H560" stroke="currentColor" opacity=".15" /><path d="M8 25V65" stroke="currentColor" stroke-width="2" /><path d="M16 37V53" stroke="currentColor" stroke-width="2" /><path d="M24 20V70" stroke="currentColor" stroke-width="2" /><path d="M32 32V58" stroke="currentColor" stroke-width="2" /><path d="M40 15V75" stroke="currentColor" stroke-width="2" /><path d="M48 27V63" stroke="currentColor" stroke-width="2" /><path d="M56 39V51" stroke="currentColor" stroke-width="2" /><path d="M64 22V68" stroke="currentColor" stroke-width="2" /><path d="M72 34V56" stroke="currentColor" stroke-width="2" /><path d="M80 17V73" stroke="currentColor" stroke-width="2" /><path d="M88 29V61" stroke="currentColor" stroke-width="2" /><path d="M96 41V49" stroke="currentColor" stroke-width="2" /><path d="M104 24V66" stroke="currentColor" stroke-width="2" /><path d="M112 36V54" stroke="currentColor" stroke-width="2" /><path d="M120 19V71" stroke="currentColor" stroke-width="2" /><path d="M128 31V59" stroke="currentColor" stroke-width="2" /><path d="M136 14V76" stroke="currentColor" stroke-width="2" /><path d="M144 26V64" stroke="currentColor" stroke-width="2" /><path d="M152 38V52" stroke="currentColor" stroke-width="2" /><path d="M160 21V69" stroke="currentColor" stroke-width="2" /><path d="M168 33V57" stroke="currentColor" stroke-width="2" /><path d="M176 16V74" stroke="currentColor" stroke-width="2" /><path d="M184 28V62" stroke="currentColor" stroke-width="2" /><path d="M192 40V50" stroke="currentColor" stroke-width="2" /><path d="M200 23V67" stroke="currentColor" stroke-width="2" /><path d="M208 35V55" stroke="currentColor" stroke-width="2" /><path d="M216 18V72" stroke="currentColor" stroke-width="2" /><path d="M224 30V60" stroke="currentColor" stroke-width="2" /><path d="M232 42V48" stroke="currentColor" stroke-width="2" /><path d="M240 25V65" stroke="currentColor" stroke-width="2" /><path d="M248 37V53" stroke="currentColor" stroke-width="2" /><path d="M256 20V70" stroke="currentColor" stroke-width="2" /><path d="M264 32V58" stroke="currentColor" stroke-width="2" /><path d="M272 15V75" stroke="currentColor" stroke-width="2" /><path d="M280 27V63" stroke="currentColor" stroke-width="2" /><path d="M288 39V51" stroke="currentColor" stroke-width="2" /><path d="M296 22V68" stroke="currentColor" stroke-width="2" /><path d="M304 34V56" stroke="currentColor" stroke-width="2" /><path d="M312 17V73" stroke="currentColor" stroke-width="2" /><path d="M320 29V61" stroke="currentColor" stroke-width="2" /><path d="M328 41V49" stroke="currentColor" stroke-width="2" /><path d="M336 24V66" stroke="currentColor" stroke-width="2" /><path d="M344 36V54" stroke="currentColor" stroke-width="2" /><path d="M352 19V71" stroke="currentColor" stroke-width="2" /><path d="M360 31V59" stroke="currentColor" stroke-width="2" /><path d="M368 14V76" stroke="currentColor" stroke-width="2" /><path d="M376 26V64" stroke="currentColor" stroke-width="2" /><path d="M384 38V52" stroke="currentColor" stroke-width="2" /><path d="M392 21V69" stroke="currentColor" stroke-width="2" /><path d="M400 33V57" stroke="currentColor" stroke-width="2" /><path d="M408 16V74" stroke="currentColor" stroke-width="2" /><path d="M416 28V62" stroke="currentColor" stroke-width="2" /><path d="M424 40V50" stroke="currentColor" stroke-width="2" /><path d="M432 23V67" stroke="currentColor" stroke-width="2" /><path d="M440 35V55" stroke="currentColor" stroke-width="2" /><path d="M448 18V72" stroke="currentColor" stroke-width="2" /><path d="M456 30V60" stroke="currentColor" stroke-width="2" /><path d="M464 42V48" stroke="currentColor" stroke-width="2" /><path d="M472 25V65" stroke="currentColor" stroke-width="2" /><path d="M480 37V53" stroke="currentColor" stroke-width="2" /><path d="M488 20V70" stroke="currentColor" stroke-width="2" /><path d="M496 32V58" stroke="currentColor" stroke-width="2" /><path d="M504 15V75" stroke="currentColor" stroke-width="2" /><path d="M512 27V63" stroke="currentColor" stroke-width="2" /><path d="M520 39V51" stroke="currentColor" stroke-width="2" /><path d="M528 22V68" stroke="currentColor" stroke-width="2" /><path d="M536 34V56" stroke="currentColor" stroke-width="2" /><path d="M544 17V73" stroke="currentColor" stroke-width="2" /><path d="M552 29V61" stroke="currentColor" stroke-width="2" /></svg><div className="login-production-foot"><span>CAPTURE</span><span>TRACE</span><span>REVIEW</span><span>DELIVER</span></div></div></div>
    <div className="login-form-wrap"><div className="login-header"><div className="login-brand"><Aperture size={28} strokeWidth={2.2} /><strong>ContentStudio<span>.</span></strong></div><ThemeControl /></div><form className="login-card" onSubmit={(event) => { event.preventDefault(); login.mutate() }}><span className="eyebrow">WELCOME BACK</span><h2>Sign in to<br />your studio.</h2><p>Your source. Your decisions. Your final cut.</p><label className="form-label" htmlFor="email">Email address</label><input id="email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" /><label className="form-label" htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Your password" />{login.isError ? <div className="form-error" role="alert"><CircleAlert size={16} />{errorMessage(login.error)}</div> : null}<Button type="submit" loading={login.isPending} className="login-submit">Enter workspace <ArrowRight size={17} /></Button><p className="login-help">Demo credentials are listed in the local handover guide.</p></form><span className="login-footer">SOURCE-FIRST PRODUCTION / PRIVATE WORKSPACE</span></div>
  </main>
}

function Workspace({ session }: { session: AuthSession }) {
  const queryClient = useQueryClient()
  const [page, setPage] = useState<Page>('studio')
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const menuRef = useRef<HTMLElement>(null)
  useEffect(() => {
    if (!mobileMenuOpen) return
    const previous = document.activeElement as HTMLElement | null
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const buttons = () => Array.from(menuRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? []).filter((button) => button.getClientRects().length > 0)
    buttons()[0]?.focus()
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); setMobileMenuOpen(false) }
      if (event.key !== 'Tab') return
      const targets = buttons()
      const first = targets[0]
      const last = targets[targets.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    const wide = window.matchMedia('(min-width: 851px)')
    const resize = () => { if (wide.matches) setMobileMenuOpen(false) }
    document.addEventListener('keydown', keydown)
    wide.addEventListener('change', resize)
    return () => { document.body.style.overflow = overflow; document.removeEventListener('keydown', keydown); wide.removeEventListener('change', resize); previous?.focus() }
  }, [mobileMenuOpen])
  const [chosenBatchId, setChosenBatchId] = useState<string | null>(null)
  const [chosenSourceId, setChosenSourceId] = useState<string | null>(null)
  const [chosenAssetId, setChosenAssetId] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const bootstrap = useQuery({ queryKey: ['bootstrap'], queryFn: api.bootstrap, refetchInterval: 30_000 })
  const sources = useQuery({ queryKey: ['sources'], queryFn: api.sources })
  const batches = useQuery({ queryKey: ['batches'], queryFn: api.batches, refetchInterval: 20_000 })
  const brands = useQuery({ queryKey: ['brands'], queryFn: api.brands })
  const logout = useMutation({ mutationFn: api.logout, onSuccess: async () => { await queryClient.cancelQueries(); queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth' }); await queryClient.resetQueries({ queryKey: ['auth'] }) } })
  const batchId = chosenBatchId === '' ? null : chosenBatchId ?? batches.data?.items[0]?.id ?? null
  const batch = useQuery({ queryKey: ['batch', batchId], queryFn: () => api.batch(batchId!), enabled: !!batchId, refetchInterval: 20_000 })
  const sourceId = chosenSourceId ?? batch.data?.source.id ?? sources.data?.items[0]?.id ?? null
  const source = useQuery({ queryKey: ['source', sourceId], queryFn: () => api.source(sourceId!), enabled: !!sourceId })

  const navigate = (next: Page) => { setPage(next); setMobileMenuOpen(false) }
  const selectSource = (id: string) => { setChosenSourceId(id); setChosenBatchId(''); setChosenAssetId(null); navigate('studio') }
  const selectBatch = (id: string, assetId?: string) => { setChosenBatchId(id); setChosenSourceId(null); setChosenAssetId(assetId ?? null); navigate('studio') }
  const notify = (message: string) => { setToast(message); window.setTimeout(() => setToast(null), 5200) }
  const items: { id: Page; label: string; icon: typeof LayoutGrid; count?: number }[] = [
    { id: 'studio', label: 'Studio', icon: Clapperboard },
    { id: 'board', label: 'Content board', icon: LayoutGrid, count: batches.data?.items.length },
    { id: 'calendar', label: 'Calendar', icon: CalendarDays },
    { id: 'library', label: 'Source library', icon: LibraryBig, count: sources.data?.items.length },
  ]
  return <div className="workspace-shell">
    <aside id="workspace-navigation" ref={menuRef} className={`sidebar ${mobileMenuOpen ? 'sidebar--open' : ''}`} role={mobileMenuOpen ? 'dialog' : undefined} aria-modal={mobileMenuOpen || undefined} aria-label="Workspace navigation">
      <div className="sidebar-top"><button className="brand" onClick={() => navigate('studio')} aria-label="Open studio"><span className="brand-symbol"><Aperture size={25} strokeWidth={2.2} /></span><span>ContentStudio<span className="brand-period">.</span></span></button><button className="mobile-close icon-button" onClick={() => setMobileMenuOpen(false)} aria-label="Close navigation"><X size={21} /></button></div>
      <div className="workspace-switch"><span className="workspace-monogram">{(bootstrap.data?.workspace.name ?? 'CS').slice(0, 2).toUpperCase()}</span><div><span className="workspace-small">WORKSPACE</span><strong>{bootstrap.data?.workspace.name ?? 'Loading workspace'}</strong></div></div>
      <div className="sidebar-group-label">WORKSPACE</div><nav className="primary-nav" aria-label="Main navigation">{items.map(({ id, label, icon: Icon, count }) => <button key={id} className={`nav-item ${page === id ? 'nav-item--active' : ''}`} aria-current={page === id ? 'page' : undefined} onClick={() => navigate(id)}><Icon size={18} strokeWidth={1.9} /><span>{label}</span>{typeof count === 'number' ? <span className="nav-count">{count}</span> : null}</button>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-appearance"><span className="eyebrow">APPEARANCE</span><ThemeControl /></div><div className="sidebar-note"><span className="eyebrow">THE EDITORIAL STANDARD</span><p>Every good idea deserves a source you can stand behind.</p><span className="note-line" /></div><div className="sidebar-user"><span className="avatar">{session.user.email[0]?.toUpperCase()}</span><div><strong>{session.user.email.split('@')[0]}</strong><span>{session.user.role} · {session.mode.toLowerCase()}</span></div><button className="icon-button" onClick={() => logout.mutate()} disabled={logout.isPending} title="Sign out" aria-label="Sign out"><LogOut size={17} /></button></div></div>
    </aside>
    {mobileMenuOpen ? <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileMenuOpen(false)} /> : null}
    <main className="main-content" inert={mobileMenuOpen || undefined}><header className="topbar"><div className="topbar-left"><button className="mobile-menu icon-button" onClick={() => setMobileMenuOpen(true)} aria-label="Open navigation" aria-expanded={mobileMenuOpen} aria-controls="workspace-navigation"><Menu size={22} /></button><span className="topbar-breadcrumb">WORKSPACE <span>/</span> {page.replace('_', ' ').toUpperCase()}</span></div><div className="topbar-right"><ThemeControl /><span className={`mode-tag ${session.mode.toLowerCase() === 'demo' ? 'mode-tag--demo' : ''}`}><span className="mode-dot" />{session.mode.toLowerCase() === 'demo' ? 'SYNTHETIC DEMO DATA' : 'CONNECTED MODE'}</span><span className="topbar-separator" /><span className="topbar-date">EDITORIAL DESK</span><span className="topbar-avatar">{session.user.email[0]?.toUpperCase()}</span></div></header>
      <div className="page-content">
        {bootstrap.isError ? <ErrorNotice error={bootstrap.error} onRetry={() => void bootstrap.refetch()} title="Workspace status unavailable" /> : null}
        {page === 'studio' ? <Studio key={batchId ?? sourceId ?? 'empty'} bootstrap={bootstrap.data} batch={batch} source={source} batches={batches.data?.items ?? []} sources={sources.data?.items ?? []} selectedAssetId={chosenAssetId} onAssetSelect={setChosenAssetId} onBatchSelect={selectBatch} onSourceSelect={selectSource} onNavigate={navigate} notify={notify} canEdit={session.user.role !== 'viewer'} brands={brands.data?.items ?? []} /> : null}
        {page === 'board' ? <Board batches={batches} onOpen={selectBatch} /> : null}
        {page === 'calendar' ? <Calendar onOpen={selectBatch} /> : null}
        {page === 'library' ? <Library sources={sources} brands={brands} onSourceSelect={selectSource} onBatchSelect={selectBatch} notify={notify} canEdit={session.user.role !== 'viewer'} workflowReady={bootstrap.data?.connection.n8n_intake === 'connected'} transcriptionReady={bootstrap.data?.connection.transcription === 'configured'} demoMode={session.mode.toLowerCase() === 'demo'} /> : null}
      </div>
    </main>
    {toast ? <div className="toast" role="status"><Command size={16} />{toast}<button onClick={() => setToast(null)} aria-label="Dismiss notification"><X size={15} /></button></div> : null}
  </div>
}

export type WorkspaceBootstrap = Bootstrap | undefined
export type BatchesQuery = ReturnType<typeof useQuery<{ items: BatchSummary[] }, Error>>
export type SourcesQuery = ReturnType<typeof useQuery<{ items: SourceAsset[] }, Error>>
