import { createContext, useContext, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import {
  Activity, ArrowDownToLine, ArrowRight, BadgeCheck, BarChart3,
  BookOpenCheck, Check, CheckCircle2, ChevronDown, ChevronRight,
  ClipboardList, Download, ExternalLink, FileCheck2, FilePlus2,
  FileSearch, Filter, Fingerprint, Flag, Globe2, Landmark, LayoutDashboard, LockKeyhole, LogOut,
  Menu, Plus, Search, Shield, ShieldAlert,
  ShieldCheck, SlidersHorizontal, Sparkles, Users, X,
} from 'lucide-react';
import { Link, Redirect, Route, Switch, useLocation, Router as WouterRouter } from 'wouter';
import {
  getDownloadWorkbookQueryKey, getGetCurrentMembershipQueryKey, getGetDashboardSummaryQueryKey, getGetEventQueryKey,
  getGetEvidenceQueryKey, getGetSiteProfileQueryKey,
  getGetSiteQueryKey, getGetSourceQueryKey, getGetTrustMatrixQueryKey,
  getHealthCheckQueryKey, getListActivityQueryKey, getListBettorsQueryKey,
  getListEntitiesQueryKey, getListEventsQueryKey, getListEvidenceQueryKey,
  getListSitesQueryKey, getListSourcesQueryKey, getListTrustScoresQueryKey,
  useCalculateTrustScore, useClassifyEvidence, useCreateBettor,
  useCreateEntity, useCreateEvent, useCreateEvidence, useCreateSite, useCreateSource,
  useDownloadWorkbook, useGetCurrentMembership, useGetDashboardSummary, useGetEvent, useGetEvidence,
  useGetSite, useGetSiteProfile, useGetSource, useGetTrustMatrix,
  useHealthCheck, useLinkSiteEntity, useListActivity, useListBettors, useListEntities,
  useListEvents, useListEvidence, useListSites, useListSources, useListTrustScores,
  useRateEvent, useRequestUploadUrl, useReviewSource, useUpdateEvent,
  useUpdateEvidence, useUpdateSite, useUpdateSource,
} from '@workspace/api-client-react';
import type {
  BettorInput, EntityInput, EventInput, EvidenceInput, LocalSessionUser, SiteInput, SourceInput, VulnerabilityFactorKey,
} from '@workspace/api-client-react';
import { ErrorBoundary } from '@/components/error-boundary';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Italiano, traduci } from '@/lib/italiano';
import NotFound from '@/pages/not-found';

const queryClient = new QueryClient();
const basePath = import.meta.env.BASE_URL.replace(/\/$/, '');
type LocalAuthContextValue = {
  user: LocalSessionUser | null;
  loading: boolean;
  refreshSession: () => Promise<LocalSessionUser | null>;
  logout: () => Promise<void>;
};
const LocalAuthContext = createContext<LocalAuthContextValue | null>(null);
function useLocalAuth() {
  const value = useContext(LocalAuthContext);
  if (!value) throw new Error('LocalAuthProvider non configurato.');
  return value;
}
function LocalAuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<LocalSessionUser | null>(null);
  const [loading, setLoading] = useState(true);
  const client = useQueryClient();
  const refreshSession = async (): Promise<LocalSessionUser | null> => {
    try {
      const response = await fetch(`${basePath}/api/auth/session`, { credentials: 'include' });
      if (!response.ok) throw new Error('Sessione non disponibile');
      const session = await response.json() as { authenticated: boolean; user: LocalSessionUser | null };
      setUser(session.authenticated ? session.user : null);
      return session.authenticated ? session.user : null;
    } catch {
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    let active = true;
    const check = async () => {
      const response = await fetch(`${basePath}/api/auth/session`, { credentials: 'include' }).catch(() => null);
      if (!active) return;
      if (!response?.ok) {
        setUser(null);
        setLoading(false);
        return;
      }
      const session = await response.json() as { authenticated: boolean; user: LocalSessionUser | null };
      if (active) {
        setUser(session.authenticated ? session.user : null);
        setLoading(false);
      }
    };
    void check();
    const interval = window.setInterval(() => { void refreshSession(); }, 60_000);
    return () => { active = false; window.clearInterval(interval); };
  }, []);
  const logout = async () => {
    await fetch(`${basePath}/api/auth/logout`, { method: 'POST', credentials: 'include' }).catch(() => undefined);
    setUser(null);
    client.clear();
  };
  return <LocalAuthContext.Provider value={{ user, loading, refreshSession, logout }}>{children}</LocalAuthContext.Provider>;
}

const navGroups = [
  { title: 'Piattaforma', items: [
    { name: 'Panoramica', path: '/dashboard', icon: LayoutDashboard },
    { name: 'Registro delle fonti', path: '/sources', icon: Globe2 },
    { name: 'Acquisizione delle evidenze', path: '/evidence', icon: FileSearch },
    { name: 'Siti di scommesse', path: '/sites', icon: Landmark },
    { name: 'Entità legali', path: '/entities', icon: Fingerprint },
  ] },
  { title: 'Analisi', items: [
    { name: 'Eventi sportivi', path: '/events', icon: Flag },
    { name: 'Profili degli scommettitori', path: '/bettors', icon: Users },
    { name: 'Indice di affidabilità', path: '/trust', icon: ShieldCheck },
  ] },
  { title: 'Estrazioni', items: [
    { name: 'Esportazioni Excel', path: '/exports', icon: ArrowDownToLine },
  ] },
];

function Button({ children, onClick, kind = 'primary', className = '', disabled = false, type = 'button', testId }: {
  children: ReactNode; onClick?: () => void; kind?: 'primary' | 'quiet' | 'outline' | 'danger'; className?: string; disabled?: boolean; type?: 'button' | 'submit'; testId?: string;
}) {
  const styles = { primary: 'btn-primary', quiet: 'btn-quiet', outline: 'btn-outline', danger: 'btn-danger' };
  return <button type={type} data-testid={testId} disabled={disabled} onClick={onClick} className={`btn ${styles[kind]} ${className}`}>{children}</button>;
}
function Status({ value }: { value?: string | null }) {
  const text = (value || 'unassessed').replaceAll('_', ' ');
  const translated = ({
    approved: 'approvato', connected: 'connesso', 'analyst confirmed': 'confermato dall’analista',
    reviewed: 'revisionato', active: 'attivo', low: 'basso', normalized: 'normalizzato',
    'in review': 'in revisione', candidate: 'candidato', medium: 'medio', new: 'nuovo',
    pending: 'in attesa', rejected: 'respinto', revoked: 'revocato', expired: 'scaduto',
    suspended: 'sospeso', high: 'alto', error: 'errore', draft: 'bozza',
    not_configured: 'non configurato', off: 'disattivato', unassessed: 'non valutato',
    synthetic: 'sintetico', authorized: 'autorizzato', confirmed: 'confermato',
  } as Record<string, string>)[text] || traduci(text);
  const tone = ['approved', 'connected', 'analyst confirmed', 'reviewed', 'active', 'low', 'normalized', 'confirmed'].includes(text) ? 'good'
    : ['in review', 'candidate', 'medium', 'new', 'pending', 'draft', 'not configured'].includes(text) ? 'warm'
    : ['rejected', 'revoked', 'expired', 'suspended', 'high', 'error'].includes(text) ? 'risk' : 'neutral';
  return <span className={`status status-${tone}`} data-testid={`status-${text.replaceAll(' ', '-')}`}><i />{translated}</span>;
}
function PageHeading({ eyebrow, title, detail, action }: { eyebrow: string; title: string; detail: string; action?: ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{detail}</p></div>{action}</div>;
}
function SkeletonRows() { return <div className="skeleton-list">{[0,1,2,3].map(i => <div className="skeleton-row" key={i}><span /><span /><span /></div>)}</div>; }
function QueryMessage({ loading, error, retry, children }: { loading?: boolean; error?: boolean; retry?: () => void; children: ReactNode }) {
  if (loading) return <SkeletonRows />;
  if (error) return <div className="empty-state"><div className="empty-icon"><Activity size={19}/></div><h3>Impossibile caricare questa sezione</h3><p>Verifica la connessione alla piattaforma e riprova.</p><Button kind="outline" onClick={retry}>Riprova</Button></div>;
  return <>{children}</>;
}
function Empty({ label, action }: { label: string; action?: ReactNode }) { return <Italiano><div className="empty-state"><div className="empty-icon"><FileCheck2 size={20}/></div><h3>Nessun {traduci(label)} presente</h3><p>I record compariranno qui quando verranno aggiunti alla piattaforma.</p>{action}</div></Italiano>; }
function Dialog({ title, subtitle, onClose, children }: { title: string; subtitle: string; onClose: () => void; children: ReactNode }) {
  return <Italiano><div className="dialog-scrim" onMouseDown={e => e.target === e.currentTarget && onClose()}><div className="dialog" role="dialog" aria-modal="true"><div className="dialog-head"><div><div className="eyebrow">RECORD DELLA PIATTAFORMA</div><h2>{traduci(title)}</h2><p>{traduci(subtitle)}</p></div><button className="icon-button" onClick={onClose} aria-label="Chiudi"><X size={18}/></button></div>{children}</div></div></Italiano>;
}
function Field({ label, name, required = false, placeholder, defaultValue, type = 'text', area = false, hint }: {
  label: string; name: string; required?: boolean; placeholder?: string; defaultValue?: string; type?: string; area?: boolean; hint?: string;
}) {
  return <label className="field"><span>{label}{required && <b> *</b>}</span>{area
    ? <textarea name={name} placeholder={placeholder} defaultValue={defaultValue} required={required} rows={3}/>
    : <input name={name} type={type} placeholder={placeholder} defaultValue={defaultValue} required={required}/ >}{hint && <small>{hint}</small>}</label>;
}
function SelectField({ label, name, choices, defaultValue }: { label: string; name: string; choices: string[]; defaultValue?: string }) {
  const choiceNames: Record<string, string> = {
    regulatory: 'normativa', sports: 'sport', operator: 'operatore', market_data: 'dati di mercato',
    other: 'altro', web: 'web', document: 'documento', email: 'e-mail',
    operator_provided: 'fornito dall’operatore', regulatory_filing: 'atto normativo',
    new: 'nuovo', classified: 'classificato', normalized: 'normalizzato', reviewed: 'revisionato',
    archived: 'archiviato', company: 'società', person: 'persona', unknown: 'sconosciuto',
    false: 'No', true: 'Sì', not_configured: 'non configurato', connected: 'connesso',
    off: 'disattivato', error: 'errore', multiple_accounts: 'più account collegati',
    eu_bank_payment: 'pagamento tramite banca UE', no_registration: 'assenza di registrazione',
    no_identity_documents: 'assenza di documenti identificativi',
    third_party_provider: 'provider di terze parti', crypto_payment_or_betting: 'pagamento o scommessa in criptovaluta',
    offshore_bank_account: 'conto bancario offshore', admin: 'amministratore',
    compliance_reviewer: 'revisore della conformità', analyst: 'analista',
    restricted_analyst: 'analista con accesso limitato', read_only: 'sola lettura',
  };
  return <label className="field"><span>{label}</span><select name={name} defaultValue={defaultValue}>{choices.map(c => <option key={c} value={c}>{choiceNames[c] || traduci(c.replaceAll('_', ' '))}</option>)}</select></label>;
}
function ErrorText({ text }: { text: string }) { return <p className="form-error" role="alert">{text}</p>; }
function dateLabel(value?: string | null) { return value ? new Date(value).toLocaleDateString('it-IT', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'; }
function money(value?: number | null) { return typeof value === 'number' ? new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(value) : '—'; }
function useSearch() { const [q, setQ] = useState(''); return { q, setQ }; }

function Sidebar() {
  const [path] = useLocation();
  const [open, setOpen] = useState(false);
  return <Italiano><><button className="mobile-menu" onClick={() => setOpen(!open)} aria-label="Apri la navigazione"><Menu size={19}/></button><aside className={`sidebar ${open ? 'sidebar-open' : ''}`}><a className="softstrategy-brand" href="https://www.softstrategy.it/" target="_blank" rel="noopener noreferrer" aria-label="Softstrategy, sito ufficiale"><img src={`${basePath}/softstrategy-logo.svg`} alt="Softstrategy" width="774" height="270"/><span>Prototipo realizzato da Softstrategy</span></a><Link href="/dashboard" className="brand sidebar-brand"><span className="brand-mark"><Shield size={18}/></span><span>CTI <b>INTELLIGENCE</b></span></Link><div className="workspace-switch"><div className="workspace-symbol">CI</div><div><b>Analisi CTI</b><span>Accesso riservato</span></div><ChevronDown size={14}/></div><div className="side-label">NAVIGAZIONE</div><nav>{navGroups.map(group => <div className="nav-group" key={group.title}><span className="nav-group-title">{group.title}</span>{group.items.map(item => { const Icon = item.icon; return <Link key={item.path} href={item.path} onClick={() => setOpen(false)} className={`nav-link ${path === item.path ? 'nav-active' : ''}`} data-testid={`link-${item.path.slice(1).replaceAll('/', '-')}`}><Icon size={16}/><span>{item.name}</span>{path === item.path && <i/>}</Link>; })}</div>)}</nav><div className="sidebar-foot"><div className="connectivity"><span className="online-dot"/> Servizio disponibile</div></div></aside>{open && <button className="mobile-scrim" onClick={() => setOpen(false)} aria-label="Chiudi navigazione"/>}</></Italiano>;
}
function AppShell({ children, title }: { children: ReactNode; title: string }) {
  const { user, logout } = useLocalAuth();
  const displayName = user?.displayName || user?.userId || 'Utente';
  return <Italiano><div className="app-frame grain"><Sidebar/><div className="app-main"><header className="topbar"><div className="crumb">CTI <ChevronRight size={13}/> <b>{traduci(title)}</b></div><div className="topbar-right"><span className="topbar-status"><span className="online-dot"/> {displayName}</span><span className="topbar-date">{new Date().toLocaleDateString('it-IT', { day: '2-digit', month: 'short', year: 'numeric' })}</span><button className="icon-button" onClick={() => void logout()} aria-label="Esci dalla piattaforma" title="Esci"><LogOut size={16}/></button></div></header><div className="notice notice-amber"><LockKeyhole size={15}/><span><b>Sessione autenticata.</b> L’accesso ai dati riservati dipende dal ruolo attivo assegnato alla piattaforma.</span></div><div className="content-wrap page-enter">{children}</div><footer className="app-footer"><span>CTI INTELLIGENCE <b>·</b> FASE 01</span><span>Inserimento manuale <span className="footer-divider">/</span> Valutazioni provvisorie</span></footer></div></div></Italiano>;
}

function Dashboard() {
  const summary = useGetDashboardSummary({ query: { queryKey: getGetDashboardSummaryQueryKey() } });
  const activity = useListActivity({ limit: 8 }, { query: { queryKey: getListActivityQueryKey({ limit: 8 }) } });
  const health = useHealthCheck({ query: { queryKey: getHealthCheckQueryKey(), staleTime: 30000 } });
  const s = summary.data;
  const cards = [
    { label: 'Fonti registrate', value: s?.sourceCount, sub: `${s?.approvedSources ?? '—'} approvate · ${s?.sourcesInReview ?? '—'} in revisione`, icon: Globe2, accent: 'sage' },
    { label: 'Record di evidenza', value: s?.evidenceCount, sub: `${s?.unclassifiedEvidence ?? '—'} da classificare`, icon: FileSearch, accent: 'ochre' },
    { label: 'Siti di scommesse', value: s?.siteCount, sub: `${s?.highRiskSites ?? '—'} ad alto rischio`, icon: Landmark, accent: 'slate' },
    { label: 'Eventi sportivi', value: s?.eventCount, sub: `${s?.highRiskEvents ?? '—'} valutati ad alto rischio`, icon: Flag, accent: 'clay' },
  ];
  return <AppShell title="Panoramica"><PageHeading eyebrow="RIEPILOGO" title="Buongiorno, analista." detail="Panoramica dei dati registrati, revisionati e da verificare." action={<Link className="btn btn-primary" href="/evidence"><Plus size={16}/> Aggiungi evidenza</Link>}/>
     <div className="workspace-banner"><div className="banner-emblem"><ShieldCheck size={19}/></div><div><b>Tracciabilità delle evidenze attiva</b><span>Autorizzazione della fonte e prontezza del connettore sono registrate separatamente.</span></div><div className="banner-right"><span className="online-dot"/>{health.isLoading ? 'Verifica API' : health.isError ? 'Stato API non disponibile' : 'API raggiungibile'}</div></div>
    <QueryMessage loading={summary.isLoading} error={summary.isError} retry={() => summary.refetch()}><section className="metric-grid">{cards.map(({label,value,sub,icon:Icon,accent}) => <article className="metric-card" key={label}><div className={`metric-icon ${accent}`}><Icon size={17}/></div><span className="metric-label">{label}</span><strong data-testid={`metric-${label.toLowerCase().replaceAll(' ','-')}`}>{value ?? '—'}</strong><small>{sub}</small></article>)}</section></QueryMessage>
     <div className="dashboard-lower"><section className="panel activity-panel"><div className="panel-heading"><div><div className="eyebrow">REGISTRO DELLE ATTIVITÀ</div><h2>Attività recenti</h2></div><Link className="subtle-link" href="/sources">Apri la piattaforma <ArrowRight size={14}/></Link></div><QueryMessage loading={activity.isLoading} error={activity.isError} retry={() => activity.refetch()}>{activity.data?.items?.length ? <div className="activity-list">{activity.data.items.map((item, i) => <article className="activity-row" key={item.id} data-testid={`activity-${item.id}`}><div className={`activity-glyph glyph-${i % 4}`}><Activity size={15}/></div><div className="activity-copy"><b>{traduci(item.action.replaceAll('_',' '))}</b><span>{traduci(item.entityLabel)} <i>·</i> {traduci(item.entityType)}</span><small>{item.actorLabel}</small></div><time>{dateLabel(item.createdAt)}</time></article>)}</div> : <Empty label="attività registrate"/>}</QueryMessage></section>
     <aside className="panel focus-panel"><div className="panel-heading"><div><div className="eyebrow">ATTENZIONE DELL’ANALISTA</div><h2>Prossime attività</h2></div><span className="count-pill">{(s?.sourcesInReview || 0) + (s?.unclassifiedEvidence || 0)}</span></div><Link href="/sources" className="focus-row"><span className="focus-number">01</span><span><b>Revisiona le fonti candidate</b><small>{s?.sourcesInReview ?? '—'} in attesa di revisione</small></span><ChevronRight size={16}/></Link><Link href="/evidence" className="focus-row"><span className="focus-number">02</span><span><b>Classifica le nuove evidenze</b><small>{s?.unclassifiedEvidence ?? '—'} record da verificare</small></span><ChevronRight size={16}/></Link><div className="provisional-note"><ShieldAlert size={15}/><span><b>Promemoria di calibrazione</b><br/>Tutti i punteggi sono provvisori. Verifica sempre le evidenze alla base.</span></div></aside></div>
  </AppShell>;
}

function SearchBar({ value, onChange, placeholder = 'Search records' }: { value: string; onChange: (s: string) => void; placeholder?: string }) {
  return <label className="search-box"><Search size={16}/><input data-testid="input-search" value={value} onChange={e => onChange(e.target.value)} placeholder={traduci(placeholder)}/>{value && <button onClick={() => onChange('')} aria-label="Cancella ricerca"><X size={14}/></button>}</label>;
}
function TableFrame({ children, minWidth = 760 }: { children: ReactNode; minWidth?: number }) { return <div className="table-scroll"><table style={{ minWidth }}>{children}</table></div>; }
function RowAction({ children, onClick }: { children: ReactNode; onClick: () => void }) { return <button className="row-action" onClick={onClick}>{children}</button>; }

function Sources() {
  const client = useQueryClient(); const { q, setQ } = useSearch(); const [modal, setModal] = useState(false); const [legalFilter, setLegalFilter] = useState('');
  const params = { q: q || undefined, legalStatus: legalFilter ? legalFilter as 'draft'|'in_review'|'approved'|'rejected'|'expired'|'revoked'|'suspended' : undefined };
  const list = useListSources(params, { query: { queryKey: getListSourcesQueryKey(params) } });
  const create = useCreateSource({ mutation: { onSuccess: () => { client.invalidateQueries({ queryKey: getListSourcesQueryKey() }); setModal(false); } } });
  const review = useReviewSource({ mutation: { onSuccess: () => client.invalidateQueries({ queryKey: getListSourcesQueryKey() }) } });
  const updateSource = useUpdateSource({ mutation: { onSuccess: () => { client.invalidateQueries({ queryKey: getListSourcesQueryKey() }); if (detailId) client.invalidateQueries({ queryKey: getGetSourceQueryKey(detailId) }); } } });
  const requestAuthorizationUpload = useRequestUploadUrl();
  const [authorizationFile, setAuthorizationFile] = useState<File | null>(null);
  const [detailId, setDetailId] = useState<number | null>(null);
  const detail = useGetSource(detailId || 0, { query: { enabled: !!detailId, queryKey: getGetSourceQueryKey(detailId || 0) } });
  const openReview = (id: number, decision: 'approve' | 'reject' | 'suspend' | 'revoke') => {
    const reason = window.prompt(`Indica la motivazione per ${({approve:'approvare',reject:'respingere',suspend:'sospendere',revoke:'revocare'} as Record<string,string>)[decision]} (almeno 3 caratteri)`);
    if (!reason || reason.trim().length < 3) return;
    review.mutate({ id, data: { decision, reason } });
  };
  return <AppShell title="Source registry"><PageHeading eyebrow="AUTHORIZATION REVIEW" title="Source registry" detail="Record who provides information, its permitted scope and current review state." action={<Button onClick={() => setModal(true)}><Plus size={16}/> Register source</Button>}/>
    <div className="notice notice-amber"><LockKeyhole size={16}/><span><b>Review is not permission.</b> Approval is a recorded workspace decision; it does not grant legal authorization. Phase 1 allows manual evidence referencing only when authorization is approved and within its validity dates; connector state is tracked separately and does not enable automated collection.</span></div>
    <section className="panel table-panel"><div className="table-tools"><SearchBar value={q} onChange={setQ} placeholder="Search provider, scope or owner"/><div className="table-info"><label className="filter-select"><Filter size={13}/><select aria-label="Filter source legal status" value={legalFilter} onChange={e => setLegalFilter(e.target.value)}><option value="">All legal states</option>{['draft','in_review','approved','rejected','expired','revoked','suspended'].map(v => <option key={v} value={v}>{v.replaceAll('_',' ')}</option>)}</select></label><span><i/> Legal state</span><span><i className="dot-outline"/> Connector state</span></div></div>
      <QueryMessage loading={list.isLoading} error={list.isError} retry={() => list.refetch()}>{list.data?.items?.length ? <TableFrame><thead><tr><th>Fornitore / fonte</th><th>Titolare e ambito</th><th>Autorizzazione</th><th>Stato legale</th><th>Connettore</th><th>Prontezza</th><th></th></tr></thead><tbody>{list.data.items.map(s => <tr key={s.id} data-testid={`row-source-${s.id}`}><td><button className="table-primary" onClick={() => setDetailId(s.id)}>{s.name}</button><small className="table-secondary">{s.provider}{s.url && <a href={s.url} target="_blank" rel="noreferrer" aria-label="Apri URL della fonte"><ExternalLink size={11}/></a>}</small></td><td><b>{s.owner}</b><small className="table-secondary truncate-cell">{s.scope}</small></td><td><b>{dateLabel(s.validFrom)} – {dateLabel(s.validUntil)}</b><small className="table-secondary">{s.dataCategories.join(', ') || s.category}</small></td><td><Status value={s.legalStatus}/></td><td><Status value={s.connectorStatus}/></td><td>{s.ingestionAllowed ? <span className="ready-label"><CheckCircle2 size={14}/> Pronto</span> : <span className="blocked-label"><LockKeyhole size={13}/> Bloccato</span>}</td><td><button className="icon-button small" onClick={() => openReview(s.id,'approve')} disabled={review.isPending} aria-label="Registra approvazione fonte"><Check size={15}/></button><button className="icon-button small" onClick={() => openReview(s.id,'reject')} disabled={review.isPending} aria-label="Respingi fonte"><X size={15}/></button><button className="icon-button small" onClick={() => openReview(s.id,'suspend')} disabled={review.isPending} aria-label="Sospendi fonte"><ShieldAlert size={14}/></button><button className="icon-button small" onClick={() => openReview(s.id,'revoke')} disabled={review.isPending} aria-label="Revoca fonte"><LockKeyhole size={14}/></button>{s.connectorStatus !== 'off' && <button className="icon-button small" onClick={() => { if (window.confirm('Disattivare il connettore per questa fonte?')) updateSource.mutate({ id: s.id, data: { connectorStatus: 'off' } }); }} aria-label="Disattiva connettore"><LockKeyhole size={14}/></button>}</td></tr>)}</tbody></TableFrame> : <Empty label="fonti registrate" action={<Button onClick={() => setModal(true)}><Plus size={15}/> Registra la prima fonte</Button>}/>}</QueryMessage>
    </section>
    {modal && <Dialog title="Register source candidate" subtitle="Capture authorization details before any ingestion is considered." onClose={() => setModal(false)}><form className="form-grid" onSubmit={async e => { e.preventDefault(); const d = new FormData(e.currentTarget); let authorizationEvidenceName: string | null = null; let authorizationEvidencePath: string | null = null; if (authorizationFile) { try { const signed = await requestAuthorizationUpload.mutateAsync({ data: { name: authorizationFile.name, size: authorizationFile.size, contentType: authorizationFile.type || 'application/octet-stream', purpose: 'authorization' } }); const uploaded = await fetch(signed.uploadURL, { method: 'PUT', headers: { 'Content-Type': authorizationFile.type || 'application/octet-stream' }, body: authorizationFile }); if (!uploaded.ok) throw new Error('Upload failed'); authorizationEvidenceName = authorizationFile.name; authorizationEvidencePath = signed.objectPath; } catch { window.alert('Caricamento della prova di autorizzazione non riuscito. La fonte non è stata registrata.'); return; } } const data: SourceInput = { name: String(d.get('name')), provider: String(d.get('provider')), url: String(d.get('url') || ''), category: String(d.get('category') || 'regulatory'), accessMethod: 'manual', owner: String(d.get('owner')), purpose: String(d.get('purpose')), scope: String(d.get('scope')), dataCategories: String(d.get('categories')).split(',').map(x => x.trim()).filter(Boolean), authorizationBasis: String(d.get('basis')), authorizationEvidenceName, authorizationEvidencePath, validFrom: String(d.get('validFrom')), validUntil: String(d.get('validUntil') || '') || null, reviewerRole: String(d.get('reviewerRole') || 'compliance_reviewer'), connectorScopes: [], secretReference: String(d.get('vault') || '') }; create.mutate({ data }); }}><Field name="name" label="Source name" required placeholder="Regulatory market bulletin"/><Field name="provider" label="Provider" required placeholder="Publishing authority"/><Field name="url" label="Public URL" placeholder="https://…"/><SelectField name="category" label="Category" choices={['regulatory','sports','operator','market_data','other']}/><Field name="owner" label="Data owner" required placeholder="Team or responsible party"/><Field name="purpose" label="Purpose" required placeholder="Compliance research and review"/><Field name="scope" label="Purpose / scope" required placeholder="Specific permitted material and limitations" area/><Field name="categories" label="Data categories" required placeholder="Licensing, market notices" hint="Separate categories with commas."/><Field name="basis" label="Authorization basis" required placeholder="Documented basis and reference" area/><label className="field full-span"><span>Authorization evidence file</span><input type="file" onChange={e => setAuthorizationFile(e.target.files?.[0] || null)}/><small>Optional evidence document stored via signed URL. Do not upload credentials.</small></label><Field name="validFrom" label="Valid from" type="date" required/><Field name="validUntil" label="Valid until" type="date"/><SelectField name="reviewerRole" label="Reviewer role" choices={['compliance_reviewer','admin']}/><Field name="vault" label="Vault reference" placeholder="vault://reference-id" hint="Reference only. Never enter credentials."/><div className="form-note full-span"><ShieldAlert size={15}/> Connector state remains off until separately configured. Approval does not grant legal permission.</div>{create.isError && <ErrorText text="Source could not be saved. Check required fields and access permissions."/>}<div className="dialog-actions"><Button kind="outline" onClick={() => setModal(false)}>Cancel</Button><Button type="submit" disabled={create.isPending || requestAuthorizationUpload.isPending}>{create.isPending || requestAuthorizationUpload.isPending ? 'Saving…' : 'Save candidate'}</Button></div></form></Dialog>}
    {detailId && <Dialog title={detail.data?.name || 'Source record'} subtitle="Authorization record and operational readiness are separate." onClose={() => setDetailId(null)}><QueryMessage loading={detail.isLoading} error={detail.isError} retry={() => detail.refetch()}>{detail.data && <div className="detail-stack"><div className="detail-pair"><span>Provider / URL</span><b>{detail.data.provider} · {detail.data.url || 'No URL recorded'}</b></div><div className="detail-pair"><span>Purpose / scope</span><b>{detail.data.purpose} · {detail.data.scope}</b></div><div className="detail-pair"><span>Data categories</span><b>{detail.data.dataCategories.join(', ')}</b></div><div className="detail-pair"><span>Validity</span><b>{dateLabel(detail.data.validFrom)} – {dateLabel(detail.data.validUntil)}</b></div><div className="detail-pair"><span>Legal review</span><Status value={detail.data.legalStatus}/></div><div className="detail-pair"><span>Connector</span><Status value={detail.data.connectorStatus}/></div><div className="detail-pair"><span>Connector scopes</span><b>{detail.data.connectorScopes.join(', ') || 'None configured'}</b></div><div className="detail-pair"><span>Authorization basis</span><b>{detail.data.authorizationBasis}</b></div><div className="detail-pair"><span>Evidence document</span><b>{detail.data.authorizationEvidenceName || 'Not attached'}</b></div><div className="detail-pair"><span>Vault reference</span><b>{detail.data.secretReference || 'Not recorded'}</b></div><div className="detail-pair"><span>Ingestion readiness</span><Status value={detail.data.ingestionAllowed ? 'approved' : 'blocked'}/></div><div className="connector-editor"><div className="eyebrow">CONNECTOR STATE · SEPARATE FROM LEGAL REVIEW</div><div className="connector-fields"><SelectField name="connectorStatus" label="Connector state" choices={['not_configured','connected','off','error']} defaultValue={detail.data.connectorStatus}/><Field name="connectorScopes" label="Authorized connector scopes" defaultValue={detail.data.connectorScopes.join(', ')} placeholder="Declared scope, comma separated"/></div><Button kind="outline" onClick={() => { const status = document.querySelector('[name="connectorStatus"]') as HTMLSelectElement; const scopes = document.querySelector('[name="connectorScopes"]') as HTMLInputElement; if (status.value === 'connected' && !scopes.value.trim()) { window.alert('Define connector scopes before enabling this source.'); return; } updateSource.mutate({ id: detailId, data: { connectorStatus: status.value as 'not_configured'|'connected'|'off'|'error', connectorScopes: scopes.value.split(',').map(s => s.trim()).filter(Boolean) } }); }}>Save connector state</Button><p className="fine-print">Phase 1 supports manual intake and authorized sources only; no live odds connector is available.</p></div><p className="fine-print">No credentials are displayed. Approval is an analyst review record, not a legal permission grant.</p></div>}</QueryMessage></Dialog>}
  </AppShell>;
}

function EvidencePage() {
  const client = useQueryClient(); const { q, setQ } = useSearch(); const [modal, setModal] = useState(false); const [statusFilter, setStatusFilter] = useState('');
  const params = { q: q || undefined, status: statusFilter ? statusFilter as 'new' | 'classified' | 'normalized' | 'reviewed' | 'archived' : undefined };
  const list = useListEvidence(params, { query: { queryKey: getListEvidenceQueryKey(params) } });
  const sources = useListSources(undefined, { query: { queryKey: getListSourcesQueryKey() } });
  const create = useCreateEvidence({ mutation: { onSuccess: () => { client.invalidateQueries({ queryKey: getListEvidenceQueryKey() }); setModal(false); } } });
  const classify = useClassifyEvidence({ mutation: { onSuccess: (_r, v) => { client.invalidateQueries({ queryKey: getGetEvidenceQueryKey(v.id) }); client.invalidateQueries({ queryKey: getListEvidenceQueryKey() }); setClassifyId(null); } } });
  const update = useUpdateEvidence({ mutation: { onSuccess: (_r, v) => { client.invalidateQueries({ queryKey: getListEvidenceQueryKey() }); client.invalidateQueries({ queryKey: getGetEvidenceQueryKey(v.id) }); } } });
  const requestUpload = useRequestUploadUrl();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState('');
  const [detailId, setDetailId] = useState<number | null>(null);
  const [classifyId, setClassifyId] = useState<number | null>(null);
  const [classifyError, setClassifyError] = useState('');
  const uploadSelected = async () => {
    if (!selectedFile) return null;
    setUploadError('');
    try {
      const signed = await requestUpload.mutateAsync({ data: { name: selectedFile.name, size: selectedFile.size, contentType: selectedFile.type || 'application/octet-stream', purpose: 'evidence' } });
      const response = await fetch(signed.uploadURL, { method: 'PUT', headers: { 'Content-Type': selectedFile.type || 'application/octet-stream' }, body: selectedFile });
      if (!response.ok) throw new Error('File upload failed');
      return { name: selectedFile.name, path: signed.objectPath };
    } catch { setUploadError('The authorized file upload failed. Your evidence record has not been submitted.'); return null; }
  };
  const detail = useGetEvidence(detailId || 0, { query: { enabled: !!detailId, queryKey: getGetEvidenceQueryKey(detailId || 0) } });
  const classifyRecord = useGetEvidence(classifyId || 0, { query: { enabled: !!classifyId, queryKey: getGetEvidenceQueryKey(classifyId || 0) } });
  return <AppShell title="Evidence intake"><PageHeading eyebrow="MANUAL MULTICHANNEL INTAKE" title="Evidence intake" detail="Capture authorized observations, classify and normalize them without automated collection." action={<Button onClick={() => setModal(true)}><Plus size={16}/> Add evidence</Button>}/>
     <div className="notice notice-sage"><BookOpenCheck size={16}/><span><b>Manual entry only.</b> No scraping, automated Telegram or Tor collection, or access to hidden or private content. Select only a source with approved legal status and current validity dates; connector status is independent and no automated connector runs in Phase 1.</span></div>
    <section className="panel table-panel"><div className="table-tools"><SearchBar value={q} onChange={setQ} placeholder="Cerca nel titolo o nel testo originale"/><label className="filter-select"><Filter size={13}/><select aria-label="Filtra lo stato delle evidenze" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}><option value="">Tutti gli stati</option>{['new','classified','normalized','reviewed','archived'].map(v => <option value={v} key={v}>{traduci(v)}</option>)}</select></label></div><QueryMessage loading={list.isLoading} error={list.isError} retry={() => list.refetch()}>{list.data?.items?.length ? <TableFrame minWidth={860}><thead><tr><th>Record di evidenza</th><th>Canale / fonte</th><th>Acquisita</th><th>Classificazione</th><th>Record collegati</th><th>Riservatezza</th><th></th></tr></thead><tbody>{list.data.items.map(e => <tr key={e.id} data-testid={`row-evidence-${e.id}`}><td><button className="table-primary" onClick={() => setDetailId(e.id)}>{e.title}</button><small className="table-secondary">EV-{String(e.id).padStart(5,'0')}</small></td><td><b>{traduci(e.channel)}</b><small className="table-secondary">{sources.data?.items.find(s => s.id === e.sourceId)?.name || (e.sourceId ? `Fonte n. ${e.sourceId}` : 'Fonte non collegata')}</small></td><td>{dateLabel(e.capturedAt)}</td><td><Status value={e.status}/></td><td><span className="linked-text">{[e.relatedSiteId && `Sito n. ${e.relatedSiteId}`,e.eventId && `Evento n. ${e.eventId}`,e.entityId && `Entità n. ${e.entityId}`].filter(Boolean).join(' · ') || 'Nessuno'}</span></td><td>{e.synthetic ? <span className="synthetic-tag">SINTETICO</span> : 'Autorizzato'}</td><td>{e.status === 'new' || e.status === 'classified' ? <RowAction onClick={() => setClassifyId(e.id)}>{e.status === 'new' ? 'Classifica' : 'Normalizza'} <ArrowRight size={13}/></RowAction> : e.status === 'normalized' ? <RowAction onClick={() => update.mutate({ id: e.id, data: { status: 'reviewed' } })}>Segna come revisionato <ArrowRight size={13}/></RowAction> : e.status === 'reviewed' ? <RowAction onClick={() => { if (window.confirm('Archiviare questo record di evidenza revisionato?')) update.mutate({ id: e.id, data: { status: 'archived' } }); }}>Archivia il record</RowAction> : <span className="table-secondary">Archiviato</span>}</td></tr>)}</tbody></TableFrame> : <Empty label="record di evidenza" action={<Button onClick={() => setModal(true)}><Plus size={15}/> Acquisisci il primo record</Button>}/>}</QueryMessage></section>
    {modal && <Dialog title="Capture evidence manually" subtitle="Enter the original record and analyst context. Use only authorized information." onClose={() => setModal(false)}><form className="form-grid" onSubmit={async e => { e.preventDefault(); const f = new FormData(e.currentTarget); const attachment = await uploadSelected(); if (selectedFile && !attachment) return; const input: EvidenceInput = { title: String(f.get('title')), channel: String(f.get('channel')), sourceId: f.get('sourceId') ? Number(f.get('sourceId')) : null, originalUrl: String(f.get('url') || '') || null, capturedAt: new Date(String(f.get('capturedAt') || new Date().toISOString())).toISOString(), rawContent: String(f.get('rawContent')), categories: String(f.get('categories') || '').split(',').map(s => s.trim()).filter(Boolean), extractedFacts: String(f.get('facts') || '').trim() ? { analystNote: String(f.get('facts')).trim() } : {}, relatedSiteId: f.get('siteId') ? Number(f.get('siteId')) : null, eventId: f.get('eventId') ? Number(f.get('eventId')) : null, entityId: f.get('entityId') ? Number(f.get('entityId')) : null, attachmentName: attachment?.name || null, attachmentPath: attachment?.path || null, synthetic: f.get('synthetic') === 'on' }; create.mutate({ data: input }); }}><Field name="title" label="Record title" required placeholder="Brief, specific description"/><SelectField name="channel" label="Channel" choices={['web','document','email','operator_provided','regulatory_filing','other']}/><label className="field"><span>Authorized source</span><select name="sourceId" defaultValue=""><option value="">No source linked</option>{sources.data?.items.map(s => <option key={s.id} value={s.id} disabled={!s.ingestionAllowed}>{s.name} · {s.legalStatus} / {s.connectorStatus}</option>)}</select><small>Unavailable sources are disabled until legal status, validity and connector state all permit ingestion.</small></label><Field name="capturedAt" label="Captured time" type="datetime-local" required/><Field name="url" label="Original URL" placeholder="Public or authorized URL only"/><Field name="categories" label="Classification categories" placeholder="Licensing, market notice"/><Field name="rawContent" label="Raw content" required placeholder="Preserve the original text or observation…" area/><Field name="facts" label="Extracted facts / analyst notes" placeholder="Separate observed facts from interpretation…" area/><Field name="siteId" label="Related site ID" type="number"/><Field name="eventId" label="Related event ID" type="number"/><Field name="entityId" label="Related entity ID" type="number"/><label className="field file-field"><span>Authorized attachment</span><input type="file" onChange={e => setSelectedFile(e.target.files?.[0] || null)}/><small>File bytes upload directly through a short-lived signed URL.</small></label><label className="check-field"><input type="checkbox" name="synthetic"/> Synthetic training record</label>{uploadError && <ErrorText text={uploadError}/ >}{create.isError && <ErrorText text="Evidence record was not saved. Check access and required fields."/>}<div className="dialog-actions"><Button kind="outline" onClick={() => setModal(false)}>Cancel</Button><Button type="submit" disabled={create.isPending || requestUpload.isPending}>{create.isPending ? 'Saving…' : <><FilePlus2 size={15}/> Capture record</>}</Button></div></form></Dialog>}
    {classifyId && <Dialog title="Classify and normalize" subtitle={classifyRecord.data?.title || 'Record analyst classification and normalized fields.'} onClose={() => { setClassifyId(null); setClassifyError(''); }}><QueryMessage loading={classifyRecord.isLoading} error={classifyRecord.isError} retry={() => classifyRecord.refetch()}>{classifyRecord.data && <form className="form-grid" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); const categories = String(f.get('categories')).split(',').map(s => s.trim()).filter(Boolean); let extractedFacts: Record<string, unknown> = {}; let normalizedFields: Record<string, unknown> = {}; try { extractedFacts = JSON.parse(String(f.get('facts') || '{}')); normalizedFields = JSON.parse(String(f.get('normalizedFields') || '{}')); } catch { setClassifyError('Facts and normalized fields must be valid JSON objects.'); return; } classify.mutate({ id: classifyId, data: { categories, extractedFacts, normalizedFields, enrichmentNotes: String(f.get('notes') || ''), status: String(f.get('status')) as 'classified'|'normalized'|'reviewed', relatedSiteId: f.get('siteId') ? Number(f.get('siteId')) : null, eventId: f.get('eventId') ? Number(f.get('eventId')) : null, entityId: f.get('entityId') ? Number(f.get('entityId')) : null } }); }}><div className="form-note full-span"><FileSearch size={14}/><span>Original record retained separately: {classifyRecord.data.channel} · captured {dateLabel(classifyRecord.data.capturedAt)}</span></div><Field name="categories" label="Classification categories" required defaultValue={classifyRecord.data.categories.join(', ')} placeholder="Licensing, market notice"/><SelectField name="status" label="Normalization state" choices={['classified','normalized','reviewed']} defaultValue={classifyRecord.data.status === 'new' ? 'classified' : classifyRecord.data.status}/><Field name="facts" label="Extracted facts (JSON object)" area defaultValue={JSON.stringify(classifyRecord.data.extractedFacts, null, 2)} hint="Observed facts only. Keep interpretation in enrichment notes."/><Field name="normalizedFields" label="Normalized fields (JSON object)" area defaultValue={JSON.stringify(classifyRecord.data.normalizedFields, null, 2)}/><Field name="notes" label="Enrichment / analyst notes" area defaultValue={classifyRecord.data.enrichmentNotes}/><Field name="siteId" label="Related site ID" type="number" defaultValue={classifyRecord.data.relatedSiteId ? String(classifyRecord.data.relatedSiteId) : ''}/><Field name="eventId" label="Related event ID" type="number" defaultValue={classifyRecord.data.eventId ? String(classifyRecord.data.eventId) : ''}/><Field name="entityId" label="Related entity ID" type="number" defaultValue={classifyRecord.data.entityId ? String(classifyRecord.data.entityId) : ''}/>{classifyError && <ErrorText text={classifyError}/ >}{classify.isError && <ErrorText text="Classification could not be saved."/>}<div className="dialog-actions"><Button kind="outline" onClick={() => setClassifyId(null)}>Cancel</Button><Button type="submit" disabled={classify.isPending}>{classify.isPending ? 'Saving…' : 'Save classification'}</Button></div></form>}</QueryMessage></Dialog>}
    {detailId && <Dialog title={detail.data?.title || 'Evidence record'} subtitle={`EV-${String(detailId).padStart(5,'0')} · ${detail.data?.channel || 'Loading record'}`} onClose={() => setDetailId(null)}><QueryMessage loading={detail.isLoading} error={detail.isError} retry={() => detail.refetch()}>{detail.data && <div className="detail-stack"><div className="detail-pair"><span>Captured</span><b>{dateLabel(detail.data.capturedAt)} · <Status value={detail.data.status}/></b></div><div className="detail-pair"><span>Source reference</span><b>{detail.data.sourceId ? `Source #${detail.data.sourceId}` : 'No source linked'}</b></div><div className="detail-pair"><span>Categories</span><b>{detail.data.categories.join(', ') || 'Not classified'}</b></div><div className="field"><span>Original raw content</span><pre className="raw-content">{detail.data.rawContent}</pre></div><div className="detail-pair"><span>Extracted facts</span><b>{JSON.stringify(detail.data.extractedFacts, null, 2)}</b></div><div className="detail-pair"><span>Normalized fields</span><b>{JSON.stringify(detail.data.normalizedFields, null, 2)}</b></div><div className="detail-pair"><span>Enrichment notes</span><b>{detail.data.enrichmentNotes || 'None recorded'}</b></div><p className="fine-print">Captured record retained as supplied. Analyst classification is distinct from original source content.</p></div>}</QueryMessage></Dialog>}
  </AppShell>;
}

function Sites() {
  const client = useQueryClient(); const { q, setQ } = useSearch(); const [modal,setModal] = useState(false); const [profileId,setProfileId] = useState<number|null>(null);
  const list = useListSites({ q: q || undefined }, { query: { queryKey: getListSitesQueryKey({ q: q || undefined }) } });
  const create = useCreateSite({ mutation: { onSuccess: () => { client.invalidateQueries({ queryKey: getListSitesQueryKey() }); setModal(false); } } });
  const profile = useGetSiteProfile(profileId || 0, { query: { enabled: !!profileId, queryKey: getGetSiteProfileQueryKey(profileId || 0) } });
  const site = useGetSite(profileId || 0, { query: { enabled: !!profileId, queryKey: getGetSiteQueryKey(profileId || 0) } });
  const entities = useListEntities(undefined, { query: { queryKey: getListEntitiesQueryKey() } });
  const linkEntity = useLinkSiteEntity({ mutation: { onSuccess: () => { client.invalidateQueries({ queryKey: getListSitesQueryKey() }); if (profileId) client.invalidateQueries({ queryKey: getGetSiteProfileQueryKey(profileId) }); } } });
  const update = useUpdateSite({ mutation: { onSuccess: (_r, v) => { client.invalidateQueries({ queryKey: getListSitesQueryKey() }); client.invalidateQueries({ queryKey: getGetSiteQueryKey(v.id) }); client.invalidateQueries({ queryKey: getGetSiteProfileQueryKey(v.id) }); } } });
  return <AppShell title="Betting sites"><PageHeading eyebrow="SITE PROFILES" title="Betting sites" detail="Inspect domain, claimed jurisdiction and evidence before assessing a site." action={<Button onClick={() => setModal(true)}><Plus size={16}/> Add site profile</Button>}/>
    <div className="notice notice-blue"><ShieldAlert size={16}/><span>Site Trust Index is a separate provisional measure. Event fraud ratings are independent and must not be conflated with this profile.</span></div>
     <section className="panel table-panel"><div className="table-tools"><SearchBar value={q} onChange={setQ} placeholder="Cerca dominio, nome o giurisdizione"/><span className="table-count">Profili: {list.data?.total ?? '—'}</span></div><QueryMessage loading={list.isLoading} error={list.isError} retry={() => list.refetch()}>{list.data?.items?.length ? <TableFrame><thead><tr><th>Sito</th><th>Giurisdizione / licenza dichiarata</th><th>Prima / ultima osservazione</th><th>Evidenze</th><th>Collegamento entità</th><th>Indice di affidabilità</th><th></th></tr></thead><tbody>{list.data.items.map(s => <tr key={s.id} data-testid={`row-site-${s.id}`}><td><button className="table-primary" onClick={() => setProfileId(s.id)}>{s.name}</button><small className="table-secondary">{s.domain}</small></td><td><b>{s.jurisdiction || 'Non specificata'}</b><small className="table-secondary">{s.licenseClaim || 'Nessuna dichiarazione registrata'}</small></td><td>{dateLabel(s.firstSeenAt)}<small className="table-secondary">Ultima: {dateLabel(s.lastSeenAt)}</small></td><td><span className="number-strong">{s.evidenceCount}</span></td><td><Status value={s.entityLinkStatus}/></td><td><b>{s.trustIndex ?? '—'}</b><small className="table-secondary"><Status value={s.riskBand}/></small></td><td><RowAction onClick={() => setProfileId(s.id)}>Apri <ArrowRight size={13}/></RowAction></td></tr>)}</tbody></TableFrame> : <Empty label="profili dei siti" action={<Button onClick={() => setModal(true)}><Plus size={15}/> Aggiungi il primo sito</Button>}/>}</QueryMessage></section>
    {modal && <Dialog title="Add betting-site profile" subtitle="Capture observed profile details. Legal entity links remain analyst-confirmed." onClose={() => setModal(false)}><form className="form-grid" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); const input: SiteInput = { domain: String(f.get('domain')), name: String(f.get('name')), description: String(f.get('description') || ''), jurisdiction: String(f.get('jurisdiction') || ''), licenseClaim: String(f.get('licenseClaim') || ''), firstSeenAt: String(f.get('firstSeenAt') || '') || null }; create.mutate({ data: input }); }}><Field name="domain" label="Domain" required placeholder="example.bet"/><Field name="name" label="Profile name" required placeholder="Observed site name"/><Field name="jurisdiction" label="Jurisdiction" placeholder="Claimed jurisdiction"/><Field name="licenseClaim" label="License claim" placeholder="Claim as observed"/><Field name="firstSeenAt" label="First seen" type="date"/><Field name="description" label="Profile notes" area placeholder="Description based on supplied evidence"/>{create.isError && <ErrorText text="Site profile could not be saved."/>}<div className="dialog-actions"><Button kind="outline" onClick={() => setModal(false)}>Cancel</Button><Button type="submit" disabled={create.isPending}>{create.isPending ? 'Saving…' : 'Save site profile'}</Button></div></form></Dialog>}
    {profileId && <Dialog title={site.data?.name || 'Site profile'} subtitle={site.data?.domain || 'Review evidence and current entity link.'} onClose={() => setProfileId(null)}><QueryMessage loading={profile.isLoading || site.isLoading} error={profile.isError || site.isError} retry={() => { profile.refetch(); site.refetch(); }}>{profile.data && site.data && <div className="detail-stack"><div className="detail-pair"><span>Jurisdiction / license</span><b>{site.data.jurisdiction || 'Unspecified'} · {site.data.licenseClaim || 'No claim'}</b></div><div className="detail-pair"><span>Evidence records</span><b>{profile.data.evidence.length} linked records</b></div><div className="evidence-mini">{profile.data.evidence.slice(0,4).map(ev => <div key={ev.id}><FileSearch size={14}/><span>{ev.title}<small>{dateLabel(ev.capturedAt)}</small></span><Status value={ev.status}/></div>)}</div><label className="field"><span>Analyst-confirmed entity link</span><select id="entity-link-select" defaultValue={site.data.legalEntityId || ''}><option value="">Select candidate entity</option>{entities.data?.items.map(en => <option key={en.id} value={en.id}>{en.name} · {en.entityType}</option>)}</select></label><Field name="rationale" label="Link rationale" placeholder="Evidence basis for analyst decision"/><div className="detail-actions"><Button kind="outline" onClick={() => { const select = document.getElementById('entity-link-select') as HTMLSelectElement; const rationale = document.querySelector('[name="rationale"]') as HTMLInputElement; if (select.value && rationale.value.trim().length >= 3) linkEntity.mutate({ id: profileId, data: { legalEntityId: Number(select.value), decision: 'candidate', rationale: rationale.value.trim() } }); else window.alert('Select an entity and provide a rationale of at least 3 characters.'); }}>Mark candidate</Button><Button onClick={() => { const select = document.getElementById('entity-link-select') as HTMLSelectElement; const rationale = document.querySelector('[name="rationale"]') as HTMLInputElement; if (select.value && rationale.value.trim().length >= 3) linkEntity.mutate({ id: profileId, data: { legalEntityId: Number(select.value), decision: 'confirm', rationale: rationale.value.trim() } }); else window.alert('Select an entity and provide a rationale of at least 3 characters.'); }}>Confirm link</Button><Button kind="quiet" onClick={() => { const description = window.prompt('Update the observed site profile description', site.data.description); if (description !== null) update.mutate({ id: profileId, data: { description } }); }}>Edit profile notes</Button></div><p className="fine-print">No automatic person attribution. Links are only made through an explicit analyst decision.</p></div>}</QueryMessage></Dialog>}
  </AppShell>;
}

function Entities() {
  const client = useQueryClient(); const { q, setQ } = useSearch(); const [modal,setModal] = useState(false);
  const list = useListEntities({ q: q || undefined }, { query: { queryKey: getListEntitiesQueryKey({ q: q || undefined }) } });
  const create = useCreateEntity({ mutation: { onSuccess: () => { client.invalidateQueries({ queryKey: getListEntitiesQueryKey() }); setModal(false); } } });
  return <AppShell title="Legal entities"><PageHeading eyebrow="CANDIDATE REVIEW" title="Legal entities" detail="Maintain evidence-backed legal-entity candidates. Site links require a separate analyst confirmation." action={<Button onClick={() => setModal(true)}><Plus size={16}/> Add entity candidate</Button>}/>
    <div className="notice notice-sage"><Fingerprint size={16}/><span><b>Candidate is not attribution.</b> Entity records are independent from site links. No person or beneficial owner is automatically inferred.</span></div>
    <section className="panel table-panel"><div className="table-tools"><SearchBar value={q} onChange={setQ} placeholder="Search entity name or registration ID"/><span className="table-count">{list.data?.total ?? '—'} entities</span></div><QueryMessage loading={list.isLoading} error={list.isError} retry={() => list.refetch()}>{list.data?.items?.length ? <TableFrame><thead><tr><th>Candidate</th><th>Entity type</th><th>Country</th><th>Registration reference</th><th>Evidence / basis</th><th>Created</th></tr></thead><tbody>{list.data.items.map(entity => <tr key={entity.id} data-testid={`row-entity-${entity.id}`}><td><b>{entity.name}</b><small className="table-secondary">Entity #{entity.id}</small></td><td><Status value={entity.entityType}/></td><td>{entity.country || '—'}</td><td className="font-mono-ui">{entity.registrationId || '—'}</td><td className="entity-notes">{entity.evidenceNotes || 'No evidence note recorded'}</td><td>{dateLabel(entity.createdAt)}</td></tr>)}</tbody></TableFrame> : <Empty label="entity candidates" action={<Button onClick={() => setModal(true)}><Plus size={15}/> Add first candidate</Button>}/>}</QueryMessage></section>
    {modal && <Dialog title="Create entity candidate" subtitle="Use records supported by supplied evidence. Do not infer personal attribution." onClose={() => setModal(false)}><form className="form-grid" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); const input: EntityInput = { name: String(f.get('name')), entityType: String(f.get('entityType')) as EntityInput['entityType'], country: String(f.get('country') || ''), registrationId: String(f.get('registrationId') || ''), evidenceNotes: String(f.get('evidenceNotes') || '') }; create.mutate({ data: input }); }}><Field name="name" label="Candidate name" required placeholder="Name as recorded in evidence"/><SelectField name="entityType" label="Candidate type" choices={['company','person','unknown']}/><Field name="country" label="Country" placeholder="Country or jurisdiction"/><Field name="registrationId" label="Registration ID" placeholder="Supplied reference only"/><Field name="evidenceNotes" label="Evidence notes" area placeholder="Record the evidence basis and uncertainty"/>{create.isError && <ErrorText text="Entity candidate could not be saved."/>}<div className="dialog-actions"><Button kind="outline" onClick={() => setModal(false)}>Cancel</Button><Button type="submit" disabled={create.isPending}>{create.isPending ? 'Saving…' : 'Save candidate'}</Button></div></form></Dialog>}
  </AppShell>;
}

function Events() {
  const client = useQueryClient(); const { q, setQ } = useSearch(); const [modal,setModal] = useState(false); const [ratingId,setRatingId] = useState<number|null>(null);
  const list = useListEvents({ q: q || undefined }, { query: { queryKey: getListEventsQueryKey({ q: q || undefined }) } });
  const create = useCreateEvent({ mutation: { onSuccess: () => { client.invalidateQueries({ queryKey: getListEventsQueryKey() }); setModal(false); } } });
  const rate = useRateEvent({ mutation: { onSuccess: () => { client.invalidateQueries({ queryKey: getListEventsQueryKey() }); setRatingId(null); } } });
  const update = useUpdateEvent({ mutation: { onSuccess: (_r, v) => { client.invalidateQueries({ queryKey: getGetEventQueryKey(v.id) }); client.invalidateQueries({ queryKey: getListEventsQueryKey() }); } } });
  const event = useGetEvent(ratingId || 0, { query: { enabled: !!ratingId, queryKey: getGetEventQueryKey(ratingId || 0) } });
  const [ratingError,setRatingError] = useState('');
  return <AppShell title="Sports events"><PageHeading eyebrow="INDEPENDENT EVENT RATINGS" title="Sports events" detail="Assess irregular market signals only against supplied, authorized market data." action={<Button onClick={() => setModal(true)}><Plus size={16}/> Add event</Button>}/>
    <div className="notice notice-amber"><Flag size={16}/><span><b>Separate event fraud rating.</b> Event ratings use the authorized market evidence supplied here. They are independent of a betting site's Trust Index and provisional for calibration.</span></div>
     <section className="panel table-panel"><div className="table-tools"><SearchBar value={q} onChange={setQ} placeholder="Cerca competizione o squadra"/><span className="table-count">Eventi: {list.data?.total ?? '—'}</span></div><QueryMessage loading={list.isLoading} error={list.isError} retry={() => list.refetch()}>{list.data?.items?.length ? <TableFrame minWidth={850}><thead><tr><th>Evento</th><th>Sport / competizione</th><th>Inizio</th><th>Mercati autorizzati</th><th>Quote anomale</th><th>Rischio evento</th><th></th></tr></thead><tbody>{list.data.items.map(ev => <tr key={ev.id} data-testid={`row-event-${ev.id}`}><td><b>{ev.home} <span className="versus">contro</span> {ev.away}</b><small className="table-secondary">Evento n. {ev.id} {ev.synthetic && <span className="synthetic-tag">SINTETICO</span>}</small></td><td>{ev.sport}<small className="table-secondary">{ev.competition}</small></td><td>{dateLabel(ev.startsAt)}</td><td><b>{ev.oddsSources}</b><small className="table-secondary">{money(ev.marketVolume)} volume</small></td><td>{ev.unusualOdds === null ? 'Non valutate' : ev.unusualOdds ? <span className="flagged"><Flag size={13}/> Segnalate</span> : 'Nessun indicatore'}</td><td><Status value={ev.riskBand}/><small className="table-secondary">Valutazione provvisoria</small></td><td><RowAction onClick={() => setRatingId(ev.id)}>Valuta l’evento <ArrowRight size={13}/></RowAction><RowAction onClick={() => { const note = window.prompt('Modifica la nota dell’analista per questo evento', ev.ratingNote); if (note !== null) update.mutate({ id: ev.id, data: { ratingNote: note } }); }}>Modifica la nota</RowAction></td></tr>)}</tbody></TableFrame> : <Empty label="eventi sportivi" action={<Button onClick={() => setModal(true)}><Plus size={15}/> Aggiungi un evento</Button>}/>}</QueryMessage></section>
    {modal && <Dialog title="Add sports event" subtitle="Supply independent event details and authorized market data." onClose={() => setModal(false)}><form className="form-grid" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); const input: EventInput = { sport: String(f.get('sport')), competition: String(f.get('competition')), home: String(f.get('home')), away: String(f.get('away')), startsAt: new Date(String(f.get('startsAt'))).toISOString(), oddsSources: Number(f.get('oddsSources') || 0), marketVolume: f.get('marketVolume') ? Number(f.get('marketVolume')) : null, unusualOdds: null, ratingNote: '', synthetic: f.get('synthetic') === 'on' }; create.mutate({ data: input }); }}><Field name="sport" label="Sport" required placeholder="Football"/><Field name="competition" label="Competition" required placeholder="Competition name"/><Field name="home" label="Home team" required placeholder="Team A"/><Field name="away" label="Away team" required placeholder="Team B"/><Field name="startsAt" label="Start time" type="datetime-local" required/><Field name="oddsSources" label="Authorized odds sources" type="number" placeholder="0"/><Field name="marketVolume" label="Market volume" type="number" placeholder="0"/><label className="check-field"><input type="checkbox" name="synthetic"/> Synthetic test record</label>{create.isError && <ErrorText text="Event record could not be saved."/>}<div className="dialog-actions"><Button kind="outline" onClick={() => setModal(false)}>Cancel</Button><Button type="submit" disabled={create.isPending}>{create.isPending ? 'Saving…' : 'Save event'}</Button></div></form></Dialog>}
    {ratingId && <Dialog title="Rate event risk" subtitle={event.data ? `${event.data.home} vs ${event.data.away}` : 'Use only supplied, authorized market data.'} onClose={() => setRatingId(null)}><QueryMessage loading={event.isLoading} error={event.isError} retry={() => event.refetch()}>{event.data && <form className="form-grid" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); const rationale = String(f.get('rationale')); const basis = String(f.get('basis')); if (rationale.length < 3 || !basis) { setRatingError('Provide both a rating rationale and supplied data basis.'); return; } rate.mutate({ id: ratingId, data: { oddsSources: Number(f.get('oddsSources')), marketVolume: Number(f.get('marketVolume')), unusualOdds: f.get('unusualOdds') === 'true', rationale, dataBasis: basis } }); }}><Field name="oddsSources" label="Authorized odds-source count" type="number" defaultValue={String(event.data.oddsSources)} required/><Field name="marketVolume" label="Market volume" type="number" defaultValue={String(event.data.marketVolume ?? '')} required/><SelectField name="unusualOdds" label="Unusual odds flag" choices={['false','true']}/><Field name="basis" label="Supplied data basis" required placeholder="Source and data period"/><Field name="rationale" label="Rating rationale" required area placeholder="Describe observed signal, not an inferred cause"/>{ratingError && <ErrorText text={ratingError}/ >}{rate.isError && <ErrorText text="Event rating was not saved. Check supplied data and permissions."/>}<div className="form-note full-span">This rating is independent from site Trust Index and is provisional for calibration.</div><div className="dialog-actions"><Button kind="outline" onClick={() => setRatingId(null)}>Cancel</Button><Button type="submit" disabled={rate.isPending}>{rate.isPending ? 'Recording…' : 'Record rating'}</Button></div></form>}</QueryMessage></Dialog>}
  </AppShell>;
}

function Bettors() {
  const client = useQueryClient(); const { q,setQ } = useSearch(); const [modal,setModal] = useState(false);
  const list = useListBettors({ q: q || undefined }, { query: { queryKey: getListBettorsQueryKey({ q: q || undefined }) } });
  const create = useCreateBettor({ mutation: { onSuccess: () => { client.invalidateQueries({ queryKey: getListBettorsQueryKey() }); setModal(false); } } });
  return <AppShell title="Bettor profiles"><PageHeading eyebrow="RESTRICTED DATASET" title="Bettor profiles" detail="Pseudonymous profiles only. Every record must be synthetic or based on explicitly authorized data." action={<Button onClick={() => setModal(true)}><Plus size={16}/> Add profile</Button>}/>
    <div className="notice notice-rust"><LockKeyhole size={16}/><span><b>Restricted access.</b> This page excludes direct identifiers. Do not enter names, account numbers, contact details or other identifying information.</span></div>
    <section className="panel table-panel"><div className="table-tools"><SearchBar value={q} onChange={setQ} placeholder="Search pseudonymous ID or operator"/><span className="restricted-chip"><LockKeyhole size={12}/> Restricted dataset</span></div><QueryMessage loading={list.isLoading} error={list.isError} retry={() => list.refetch()}>{list.data?.items?.length ? <TableFrame minWidth={850}><thead><tr><th>Pseudonymous ID</th><th>Operator</th><th>Period</th><th>Average bet</th><th>Gross winnings</th><th>Win rate</th><th>Data basis</th><th></th></tr></thead><tbody>{list.data.items.map(b => <tr key={b.id} data-testid={`row-bettor-${b.id}`}><td><b className="font-mono-ui">{b.pseudonymousId}</b><small className="table-secondary">{b.synthetic && <span className="synthetic-tag">SYNTHETIC</span>} {b.riskNote}</small></td><td>{b.operator}</td><td>{dateLabel(b.periodStart)} – {dateLabel(b.periodEnd)}</td><td>{money(b.averageBet)}</td><td>{money(b.grossWinnings)}</td><td>{(b.winRate * 100).toFixed(1)}%</td><td className="entity-notes">{b.dataBasis}</td><td><Status value={b.synthetic ? 'synthetic' : 'authorized'}/></td></tr>)}</tbody></TableFrame> : <Empty label="pseudonymous bettor profiles" action={<Button onClick={() => setModal(true)}><Plus size={15}/> Add profile</Button>}/>}</QueryMessage></section>
    {modal && <Dialog title="Add restricted profile" subtitle="Use a pseudonymous identifier and record the specific data basis." onClose={() => setModal(false)}><form className="form-grid" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); const input: BettorInput = { pseudonymousId: String(f.get('pseudonymousId')), operator: String(f.get('operator')), periodStart: new Date(String(f.get('periodStart'))).toISOString(), periodEnd: new Date(String(f.get('periodEnd'))).toISOString(), averageBet: Number(f.get('averageBet')), grossWinnings: Number(f.get('grossWinnings')), winRate: Number(f.get('winRate')) / 100, dataBasis: String(f.get('dataBasis')), synthetic: f.get('synthetic') === 'on', riskNote: String(f.get('riskNote') || '') }; create.mutate({ data: input }); }}><Field name="pseudonymousId" label="Pseudonymous ID" required placeholder="P-7F2A"/><Field name="operator" label="Operator" required placeholder="Operator name"/><Field name="periodStart" label="Period start" type="date" required/><Field name="periodEnd" label="Period end" type="date" required/><Field name="averageBet" label="Average bet" type="number" required placeholder="0.00"/><Field name="grossWinnings" label="Gross winnings" type="number" required placeholder="0.00"/><Field name="winRate" label="Win rate (%)" type="number" required placeholder="0–100"/><Field name="dataBasis" label="Data basis" required area placeholder="Authorization reference or synthetic methodology"/><Field name="riskNote" label="Analyst note" area placeholder="Optional contextual note"/><label className="check-field"><input type="checkbox" name="synthetic"/> Synthetic data record</label>{create.isError && <ErrorText text="Profile was not saved. Ensure data basis and pseudonymous ID are present."/>}<div className="dialog-actions"><Button kind="outline" onClick={() => setModal(false)}>Cancel</Button><Button type="submit" disabled={create.isPending}>{create.isPending ? 'Saving…' : 'Save restricted profile'}</Button></div></form></Dialog>}
  </AppShell>;
}

function Trust() {
  const client = useQueryClient(); const matrix = useGetTrustMatrix({ query: { queryKey: getGetTrustMatrixQueryKey() } });
  const scores = useListTrustScores(undefined, { query: { queryKey: getListTrustScoresQueryKey() } });
  const sites = useListSites(undefined, { query: { queryKey: getListSitesQueryKey() } });
  const calculate = useCalculateTrustScore({ mutation: { onSuccess: () => { client.invalidateQueries({ queryKey: getListTrustScoresQueryKey() }); client.invalidateQueries({ queryKey: getListSitesQueryKey() }); } } });
  const [modal,setModal] = useState(false);
  const factors = matrix.data?.vulnerabilityFactors || [
    { key:'multiple_accounts', label:'Collegamento di più account a un unico conto utente', weight:1 },
    { key:'eu_bank_payment', label:'Pagamento mediante conto corrente bancario UE', weight:1 },
    { key:'no_registration', label:'Assenza di registrazione', weight:1 },
    { key:'no_identity_documents', label:'Assenza di iscrizione mediante documenti di riconoscimento', weight:1 },
    { key:'third_party_provider', label:'Pagamento mediante provider terze parti', weight:1 },
    { key:'crypto_payment_or_betting', label:'Pagamento e piazzamento mediante criptovalute', weight:1 },
    { key:'offshore_bank_account', label:'Pagamento con conto corrente offshore', weight:1 },
  ];
   return <AppShell title="Indice di affidabilità"><PageHeading eyebrow="MODELLO DI VULNERABILITÀ E MINACCIA" title="Indice di affidabilità" detail="Sette fattori binari di vulnerabilità ponderati, tre indicatori di minaccia e un indice normalizzato del sito." action={<Button onClick={() => setModal(true)}><Sparkles size={15}/> Calcola punteggio provvisorio</Button>}/>
     <div className="notice notice-amber"><ShieldAlert size={16}/><span><b>Provvisorio, da calibrare.</b> I punteggi sono valutazioni dell’analista, non decisioni definitive. L’Indice di affidabilità riguarda il singolo sito ed è distinto dalle valutazioni degli eventi sportivi.</span></div>
     <section className="trust-overview"><article className="panel trust-explainer"><div className="eyebrow">STRUTTURA DEL MODELLO</div><h2>Un’unica scala normalizzata.<br/>Fattori visibili.</h2><p>Le componenti di vulnerabilità e minaccia restano verificabili. L’Indice di affidabilità ponderato e normalizzato varia da 0 a 100; esamina i fattori e la nota di calibrazione prima dell’uso.</p><div className="model-stats"><div><b>07</b><span>fattori binari di vulnerabilità</span></div><div><b>03</b><span>indicatori di minaccia</span></div><div><b>0–100</b><span>indice normalizzato</span></div></div></article><article className="panel factor-panel"><div className="panel-heading"><div><div className="eyebrow">MATRICE DI VULNERABILITÀ</div><h2>Fattori ponderati</h2></div><span className="count-pill">{factors.length}</span></div><QueryMessage loading={matrix.isLoading} error={matrix.isError} retry={() => matrix.refetch()}><div className="factor-list">{factors.map(f => <div key={f.key}><span className="factor-check"><Check size={12}/></span><b>{f.label}</b><span className="factor-weight">PESO {f.weight}</span></div>)}</div><p className="matrix-note">{matrix.data?.calibrationNotice || 'Le definizioni del modello sono provvisorie. Verifica fattori e pesi prima di interpretare i risultati.'}</p></QueryMessage></article></section>
     <section className="panel table-panel trust-results"><div className="panel-heading"><div><div className="eyebrow">ULTIMI CALCOLI</div><h2>Valutazioni dei siti</h2></div><span className="provisional-chip">PROVVISORIO</span></div><QueryMessage loading={scores.isLoading} error={scores.isError} retry={() => scores.refetch()}>{scores.data?.items?.length ? <TableFrame minWidth={820}><thead><tr><th>Sito</th><th>Indice di affidabilità</th><th>Fascia</th><th>Vulnerabilità</th><th>Minaccia</th><th>Calcolato</th><th>Nota dell’analista</th></tr></thead><tbody>{scores.data.items.map(score => <tr key={score.id} data-testid={`row-trust-score-${score.id}`}><td><b>{sites.data?.items.find(s => s.id === score.siteId)?.name || `Sito n. ${score.siteId}`}</b></td><td><span className="trust-number">{score.trustIndex}</span><span className="score-track"><i style={{ width: `${score.trustIndex}%` }}/></span></td><td><Status value={score.trustBand}/></td><td>{score.vulnerabilityScore} <small className="table-secondary">{score.vulnerabilityBand}</small></td><td>{score.threatScore} <small className="table-secondary">{score.threatBand}</small></td><td>{dateLabel(score.computedAt)}</td><td className="entity-notes">{score.analystNote || score.calibrationNotice}</td></tr>)}</tbody></TableFrame> : <Empty label="calcoli dell’Indice di affidabilità" action={<Button onClick={() => setModal(true)}>Calcola il primo punteggio</Button>}/>}</QueryMessage></section>
    {modal && <Dialog title="Calculate provisional Trust Index" subtitle="Select a site, assess all seven factors and state the data basis." onClose={() => setModal(false)}><form className="form-grid trust-form" onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); const selected = factors.map(factor => ({ key: factor.key as VulnerabilityFactorKey, present: f.get(`factor-${factor.key}`) === 'on' })); const selectedSite = Number(f.get('siteId')); if (!selectedSite || selected.length !== 7) return; calculate.mutate({ data: { siteId: selectedSite, vulnerabilityFactors: selected, threatMetrics: { averageBet: Number(f.get('averageBet') || 0), grossWinnings: Number(f.get('grossWinnings') || 0), winRate: Number(f.get('winRate') || 0) / 100 }, analystNote: String(f.get('analystNote') || '') } }, { onSuccess: () => setModal(false) }); }}><label className="field full-span"><span>Site profile</span><select name="siteId" required defaultValue=""><option value="">Choose a recorded site</option>{sites.data?.items.map(s => <option key={s.id} value={s.id}>{s.name} · {s.domain}</option>)}</select></label><div className="factor-edit-list full-span">{factors.map(f => <label key={f.key}><input type="checkbox" name={`factor-${f.key}`}/><span><b>{f.label}</b><small>Weight {f.weight}</small></span></label>)}</div><div className="form-section-label full-span">Threat metrics supplied for this site</div><Field name="averageBet" label="Average bet" type="number" placeholder="0"/><Field name="grossWinnings" label="Gross winnings" type="number" placeholder="0"/><Field name="winRate" label="Win rate (%)" type="number" placeholder="0–100"/><Field name="analystNote" label="Analyst note and data basis" area placeholder="Record evidence basis, uncertainty and calibration context"/>{calculate.isError && <ErrorText text="Score calculation failed. Review all seven factors and site data."/>}<div className="form-note full-span">The normalized score is provisional for calibration and must be interpreted with its detail.</div><div className="dialog-actions"><Button kind="outline" onClick={() => setModal(false)}>Cancel</Button><Button type="submit" disabled={calculate.isPending}>{calculate.isPending ? 'Calculating…' : 'Calculate score'}</Button></div></form></Dialog>}
  </AppShell>;
}

function Exports() {
  const [scope, setScope] = useState<'all'|'sources'|'evidence'|'sites'|'entities'|'events'|'bettors'|'trust'|'audit'>('all');
  const [includeRestricted, setIncludeRestricted] = useState(false);
  const membership = useGetCurrentMembership({
    query: { queryKey: getGetCurrentMembershipQueryKey(), staleTime: 30000 },
  });
  const permittedRoles = ['admin', 'compliance_reviewer', 'restricted_analyst'];
  const canExportRestricted = membership.data?.status === 'active' &&
    permittedRoles.includes(membership.data.role || '');
  const workbook = useDownloadWorkbook(
    { scope, includeRestricted },
    { query: { enabled: false, queryKey: getDownloadWorkbookQueryKey({ scope, includeRestricted }) } },
  );
  const [downloadError, setDownloadError] = useState('');
  const download = async () => {
    setDownloadError('');
    try {
      const result = await workbook.refetch();
      if (result.error) {
        const status = 'status' in result.error ? result.error.status : undefined;
        if (status === 403) {
          throw new Error('Il ruolo o lo stato del profilo non consente questa esportazione.');
        }
        throw result.error;
      }
      if (!result.data) throw new Error('Workbook unavailable');
      const blob = result.data instanceof Blob ? result.data : new Blob([result.data as BlobPart], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement('a'); anchor.href = href; anchor.download = `cti-intelligence-${scope}-${new Date().toISOString().slice(0,10)}.xlsx`; document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(href);
    } catch (error) {
      setDownloadError(error instanceof Error && error.message.startsWith('Il ruolo')
        ? error.message
        : 'Non è stato possibile generare il file Excel. Verifica l’accesso e riprova.');
    }
  };
  const sheets = [
    ['Fonti', 'Stato dell’autorizzazione, connettore, ambito e riferimento al caveau'],
    ['Evidenze', 'Record originali, classificazione, normalizzazione e collegamenti'],
    ['Siti', 'Osservazioni del profilo, collegamento legale e indice di affidabilità'],
    ['Entità', 'Entità legali candidate e note sulle evidenze'],
    ['Eventi', 'Dati di mercato autorizzati e valutazione provvisoria separata'],
    ['Scommettitori', 'Profili pseudonimi: inclusi solo per ruoli autorizzati e su richiesta esplicita'],
    ['Indice', 'Fattori, indicatori, punteggio normalizzato e calibrazione'],
    ['Attività', 'Azioni registrate, operatore, entità e data'],
    ['Metodologia', 'Formule, scale, limiti e avvertenze sulla calibrazione'],
  ];
  const scopeBySheet: Record<string, string | string[]> = {
    Fonti: 'sources', Evidenze: 'evidence', Siti: 'sites', Entità: 'entities',
    Eventi: 'events', Scommettitori: 'bettors', Indice: 'trust', Attività: 'audit',
    Metodologia: ['events', 'trust'],
  };
  const visibleSheets = sheets.filter(([name]) =>
    (name !== 'Scommettitori' || canExportRestricted) &&
    (scope === 'all' ||
      (Array.isArray(scopeBySheet[name])
        ? (scopeBySheet[name] as string[]).includes(scope)
        : scopeBySheet[name] === scope)),
  );
  const scopeLabels: Record<string, string> = {
    sources: 'Fonti', evidence: 'Evidenze', sites: 'Siti', entities: 'Entità',
    events: 'Eventi', bettors: 'Scommettitori', trust: 'Indice', audit: 'Attività',
  };
  return <AppShell title="Esportazioni Excel"><PageHeading eyebrow="ESTRAZIONE TRACCIABILE" title="Esportazioni Excel" detail="Genera un file con più fogli, tracciabilità delle fonti e un ambito esplicito."/>
    <div className="export-layout">
      <section className="panel export-config">
        <div className="export-kicker"><div className="export-icon"><Download size={20}/></div><div><div className="eyebrow">CREAZIONE DEL FILE EXCEL</div><h2>Crea un’estrazione</h2></div></div>
        <p>Seleziona l’ambito dei dati. Il risultato sarà un file Excel scaricabile. L’accesso richiede un account autorizzato.</p>
        <label className="field"><span>Ambito dell’estrazione</span><select value={scope} onChange={e => { const next = e.target.value as typeof scope; setScope(next); if (next !== 'all' && next !== 'bettors') setIncludeRestricted(false); }}>
          <option value="all">Tutti i fogli disponibili</option>
          {['sources','evidence','sites','entities','events','trust','audit', ...(canExportRestricted ? ['bettors'] : [])].map(option => <option value={option} key={option}>{scopeLabels[option]}</option>)}
        </select></label>
        {canExportRestricted && (scope === 'all' || scope === 'bettors') ? (
          <label className="restricted-toggle"><input type="checkbox" checked={includeRestricted} onChange={e => setIncludeRestricted(e.target.checked)}/><span><LockKeyhole size={16}/><span><b>Includi i dati riservati degli scommettitori</b><small>Visibili solo ai ruoli autorizzati; l’inclusione richiede una selezione esplicita.</small></span></span></label>
        ) : !canExportRestricted ? (
          <p className="export-role-note">I profili riservati non sono disponibili per il ruolo attuale. Ruoli abilitati: amministratore, revisore della conformità e analista con accesso limitato.</p>
        ) : null}
        {downloadError && <ErrorText text={downloadError}/>}
        <Button onClick={download} disabled={workbook.isFetching} className="download-button">{workbook.isFetching ? 'Preparazione del file Excel…' : <><Download size={16}/> Genera il file Excel</>}</Button>
        <div className="export-footnote"><ShieldCheck size={14}/> L’esportazione viene registrata nel registro delle attività.</div>
      </section>
      <aside className="panel sheet-panel"><div className="eyebrow">DATI INCLUSI / TRACCIABILITÀ</div><h2>Contenuto del file Excel</h2>
        <div className="sheet-list">{visibleSheets.map(([name,detail],i) => <div key={name}><span className="sheet-number">0{i+1}</span><span><b>{name}</b><small>{detail}</small></span><FileCheck2 size={15}/></div>)}</div>
        <div className="lineage-callout"><FileSearch size={17}/><span><b>Tracciabilità integrata</b><small>Ambito, identificativi e riferimenti alle fonti restano nei dati esportati.</small></span></div>
      </aside>
    </div>
  </AppShell>;
}
function WorkspaceRoutes() {
  return <Switch>
    <Route path="/" component={() => <Redirect to="/dashboard"/>}/>
    <Route path="/dashboard" component={Dashboard}/>
    <Route path="/sources" component={Sources}/>
    <Route path="/evidence" component={EvidencePage}/>
    <Route path="/sites" component={Sites}/>
    <Route path="/entities" component={Entities}/>
    <Route path="/events" component={Events}/>
    <Route path="/bettors" component={Bettors}/>
    <Route path="/trust" component={Trust}/>
    <Route path="/exports" component={Exports}/>
    <Route component={NotFound}/>
  </Switch>;
}
function PublicLanding() {
  const { loading, user } = useLocalAuth();
  if (loading) return <div className="auth-loading" role="status">Verifica della sessione…</div>;
  if (user) return <Redirect to="/dashboard"/>;
  return <main className="auth-landing">
    <a className="auth-brand" href={`${basePath || ''}/`}><img src={`${basePath}/softstrategy-logo.svg`} alt="Softstrategy"/></a>
    <div className="auth-landing-content">
      <div className="eyebrow">PIATTAFORMA DI ANALISI CTI</div>
      <h1>Analisi autorizzata.<br/>Evidenze tracciabili.</h1>
      <p>Una piattaforma per registrare fonti autorizzate, conservare le evidenze e verificare valutazioni ed esportazioni.</p>
      <div className="auth-landing-actions">
        <Link className="btn btn-primary" href="/sign-in">Accedi alla piattaforma <ArrowRight size={16}/></Link>
      </div>
      <p className="auth-landing-note">Accesso locale con ID utente e password. Gli account sono configurati dall’amministratore.</p>
    </div>
  </main>;
}
function SignInPage() {
  const { loading, user, refreshSession } = useLocalAuth();
  const [, setLocation] = useLocation();
  const client = useQueryClient();
  const [userId, setUserId] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  if (loading) return <div className="auth-loading" role="status">Verifica della sessione…</div>;
  if (user) return <Redirect to="/dashboard"/>;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const response = await fetch(`${basePath}/api/auth/login`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ userId, password }),
      });
      const result = await response.json().catch(() => null) as { error?: string } | null;
      if (!response.ok) throw new Error(result?.error || 'Accesso non riuscito. Verifica le credenziali.');
      await refreshSession();
      client.clear();
      setLocation('/dashboard');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Accesso non riuscito. Riprova.');
    } finally {
      setSubmitting(false);
    }
  };
  return <main className="auth-page">
    <Link className="auth-back-link" href="/">← Torna alla pagina iniziale</Link>
    <section className="local-login-card">
      <img className="local-login-logo" src={`${basePath}/softstrategy-logo.svg`} alt="Softstrategy"/>
      <div className="eyebrow">PIATTAFORMA CTI</div>
      <h1>Accedi alla piattaforma</h1>
      <p>Inserisci le credenziali locali assegnate dall’amministratore.</p>
      <form className="local-login-form" onSubmit={submit}>
        <label className="field">
          <span>ID utente</span>
          <input autoComplete="username" name="userId" value={userId} onChange={event => setUserId(event.target.value)} required minLength={3} maxLength={64} autoCapitalize="none" spellCheck={false}/>
        </label>
        <label className="field">
          <span>Password</span>
          <input autoComplete="current-password" name="password" type="password" value={password} onChange={event => setPassword(event.target.value)} required maxLength={256}/>
        </label>
        {error && <ErrorText text={error}/>}
        <Button type="submit" disabled={submitting || !userId || !password}>{submitting ? 'Accesso in corso…' : 'Accedi'}</Button>
      </form>
      <div className="local-login-note"><LockKeyhole size={14}/> Accesso protetto da sessione locale e ruolo assegnato.</div>
    </section>
  </main>;
}
function WorkspaceGate() {
  const { loading, user } = useLocalAuth();
  if (loading) return <div className="auth-loading" role="status">Verifica della sessione…</div>;
  if (!user) return <Redirect to="/sign-in"/>;
  return <Router/>;
}
function ApplicationRoutes() {
  return <Switch>
    <Route path="/sign-in" component={SignInPage}/>
    <Route path="/sign-up"><Redirect to="/sign-in"/></Route>
    <Route path="/" component={PublicLanding}/>
    <Route component={WorkspaceGate}/>
  </Switch>;
}
function Router() {
  const [location] = useLocation();
  return <ErrorBoundary resetKey={location}><Italiano><WorkspaceRoutes/></Italiano></ErrorBoundary>;
}
function App() {
  return <QueryClientProvider client={queryClient}><TooltipProvider><WouterRouter base={basePath}><LocalAuthProvider><ApplicationRoutes/></LocalAuthProvider></WouterRouter><Toaster/></TooltipProvider></QueryClientProvider>;
}

export default App;
