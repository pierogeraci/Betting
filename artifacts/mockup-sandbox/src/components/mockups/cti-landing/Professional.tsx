import { ArrowDownRight, ArrowRight, ArrowUpRight, BadgeCheck, FileCheck2, Fingerprint, LockKeyhole, Search, ShieldCheck } from "lucide-react";
import "./_group.css";

export function Professional() {
  return (
    <main className="cti-professional">
      <div className="cp-shell">
        <header className="cp-header">
          <a className="cp-brand" href="#" aria-label="Softstrategy — pagina iniziale">
            <img src="/__mockup/softstrategy-logo.svg" alt="Softstrategy" />
          </a>
          <nav className="cp-nav" aria-label="Navigazione principale">
            <a href="#metodo">Metodo</a>
            <a href="#ambiti">Ambiti di analisi</a>
          </nav>
          <div className="cp-header-right">
            <span className="cp-access-label"><LockKeyhole size={13} aria-hidden="true" /> Area riservata</span>
            <a className="cp-header-link" href="/sign-in">Accedi <ArrowUpRight size={15} aria-hidden="true" /></a>
          </div>
        </header>

        <section className="cp-hero" aria-labelledby="cp-title">
          <div className="cp-intro">
            <div className="cp-kicker"><span className="cp-kicker-mark" /> SOFTSTRATEGY <span className="cp-kicker-divider">/</span> GAMBLING INTELLIGENCE</div>
            <h1 id="cp-title">Dati ordinati.<br /><em>Valutazioni</em> difendibili.</h1>
            <p className="cp-lede">
              Uno spazio di lavoro controllato per analizzare il gioco online: dalle autorizzazioni delle fonti alla raccolta delle evidenze, fino a valutazioni documentate ed esportazioni strutturate.
            </p>
            <div className="cp-hero-actions">
              <a className="cp-primary" href="/sign-in">Accedi alla piattaforma <ArrowRight size={17} aria-hidden="true" /></a>
              <a className="cp-secondary" href="#metodo">Esplora il metodo <ArrowDownRight size={16} aria-hidden="true" /></a>
            </div>
            <div className="cp-trust-line">
              <span className="cp-trust-icon"><ShieldCheck size={16} aria-hidden="true" /></span>
              <span><strong>Accesso locale</strong><br />ID utente e password, account configurati dall’amministratore.</span>
            </div>
          </div>

          <div className="cp-preview-wrap" aria-label="Anteprima illustrativa dell’area di lavoro">
            <div className="cp-preview-topline">
              <span className="cp-preview-caption">AREA DI LAVORO</span>
              <span className="cp-preview-state"><span /> ESEMPIO DIMOSTRATIVO</span>
            </div>
            <div className="cp-workspace">
              <aside className="cp-workspace-rail" aria-hidden="true">
                <div className="cp-rail-logo">S</div>
                <span className="cp-rail-active"><Search size={16} /></span>
                <span><FileCheck2 size={16} /></span>
                <span><Fingerprint size={16} /></span>
              </aside>
              <div className="cp-workspace-main">
                <div className="cp-ws-heading">
                  <div>
                    <span className="cp-ws-overline">PANORAMICA</span>
                    <h2>Registro di analisi</h2>
                  </div>
                  <span className="cp-ws-date">Anteprima</span>
                </div>
                <div className="cp-workflow">
                  <div className="cp-workflow-step">
                    <span className="cp-step-icon"><BadgeCheck size={16} /></span>
                    <span className="cp-step-copy"><b>Fonte autorizzata</b><small>Permessi documentati</small></span>
                    <span className="cp-step-mark">01</span>
                  </div>
                  <div className="cp-flow-rule" />
                  <div className="cp-workflow-step">
                    <span className="cp-step-icon cp-step-icon-sand"><FileCheck2 size={16} /></span>
                    <span className="cp-step-copy"><b>Evidenza tracciabile</b><small>Riferimenti conservati</small></span>
                    <span className="cp-step-mark">02</span>
                  </div>
                  <div className="cp-flow-rule" />
                  <div className="cp-workflow-step">
                    <span className="cp-step-icon cp-step-icon-outline"><Search size={16} /></span>
                    <span className="cp-step-copy"><b>Valutazione verificabile</b><small>Esiti con contesto</small></span>
                    <span className="cp-step-mark">03</span>
                  </div>
                </div>
                <div className="cp-ws-bottom">
                  <div className="cp-record">
                    <span className="cp-record-label">SCHEDA ESEMPLIFICATIVA</span>
                    <div className="cp-record-row"><span>Entità</span><b>Elemento dimostrativo</b></div>
                    <div className="cp-record-row"><span>Stato</span><i><span /> In revisione</i></div>
                  </div>
                  <div className="cp-index">
                    <span className="cp-index-label">TRACCIABILITÀ</span>
                    <div className="cp-index-lines"><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /><i /></div>
                    <span className="cp-index-foot">Riferimenti collegati</span>
                  </div>
                </div>
              </div>
            </div>
            <p className="cp-preview-footnote">Contenuti illustrativi, non riferiti a soggetti o attività reali.</p>
            <div className="cp-preview-stamp"><span>CONTROLLO</span><b>01</b></div>
          </div>
        </section>

        <section className="cp-method" id="metodo" aria-label="Principi di lavoro">
          <div className="cp-method-intro">
            <span className="cp-section-number">01 <i /> APPROCCIO</span>
            <h2>Un percorso leggibile,<br />dalla fonte al report.</h2>
          </div>
          <div className="cp-method-copy">
            <p>Ogni passaggio mantiene il proprio contesto: ciò che è stato consultato, ciò che è stato raccolto e come si è arrivati a una valutazione.</p>
            <div className="cp-capabilities" id="ambiti">
              <span><b>A</b> Siti e operatori</span>
              <span><b>B</b> Entità e attività</span>
              <span><b>C</b> Eventi sportivi</span>
              <span><b>D</b> Profili e report Excel</span>
            </div>
          </div>
        </section>

        <footer className="cp-footer">
          <span>SOFTSTRATEGY <i>·</i> CTI GAMBLING INTELLIGENCE</span>
          <span>Workspace controllato <i>·</i> Accesso per account configurati</span>
        </footer>
      </div>
      <style>{`
        .cti-professional {
          --cp-ink: #1d2c3a;
          --cp-muted: #65716e;
          --cp-line: #d8ddd6;
          --cp-paper: #f3f3ed;
          --cp-white: #fbfcf8;
          --cp-navy: #203c53;
          --cp-teal: #386c66;
          --cp-ochre: #b28b53;
          min-height: 100vh;
          color: var(--cp-ink);
          background:
            radial-gradient(ellipse at 80% 30%, rgba(201, 211, 197, .38), transparent 33%),
            linear-gradient(125deg, #f5f4ee 0%, #edf1eb 55%, #f4f3ec 100%);
          font-family: "DM Sans", sans-serif;
          overflow: hidden;
        }
        .cti-professional *, .cti-professional *::before, .cti-professional *::after { box-sizing: border-box; }
        .cti-professional a { color: inherit; text-decoration: none; }
        .cp-shell { width: min(1160px, calc(100% - 80px)); margin: 0 auto; }
        .cp-header { min-height: 96px; display: flex; align-items: center; border-bottom: 1px solid rgba(32, 60, 83, .14); }
        .cp-brand { display: block; width: 132px; height: 48px; overflow: hidden; flex: 0 0 auto; }
        .cp-brand img { display: block; width: 160px; max-width: none; height: auto; }
        .cp-nav { display: flex; gap: 33px; margin-left: 58px; color: #687471; font-size: 12px; font-weight: 600; }
        .cp-nav a { transition: color .2s ease; }
        .cp-nav a:hover, .cp-nav a:focus-visible { color: var(--cp-teal); }
        .cp-header-right { margin-left: auto; display: flex; align-items: center; gap: 27px; }
        .cp-access-label { display: flex; align-items: center; gap: 8px; color: #737d78; font: 500 10px/1 "DM Mono", monospace; letter-spacing: .07em; text-transform: uppercase; }
        .cp-access-label svg { color: var(--cp-teal); }
        .cp-header-link { display: inline-flex; align-items: center; gap: 7px; color: var(--cp-navy); font-size: 12px; font-weight: 700; }
        .cp-header-link svg { transition: transform .2s ease; }
        .cp-header-link:hover svg { transform: translate(2px, -2px); }
        .cp-hero { display: grid; grid-template-columns: minmax(0, 1fr) minmax(440px, .96fr); gap: 68px; align-items: center; padding: 72px 0 75px; }
        .cp-intro { padding: 0 0 8px 3px; }
        .cp-kicker { display: flex; align-items: center; color: #697670; font: 500 9px/1.5 "DM Mono", monospace; letter-spacing: .13em; }
        .cp-kicker-mark { width: 18px; height: 2px; margin-right: 10px; background: var(--cp-ochre); }
        .cp-kicker-divider { margin: 0 9px; color: #a4aaa3; }
        .cp-intro h1 { margin: 26px 0 20px; color: var(--cp-ink); font: 700 clamp(42px, 5vw, 62px)/1.02 Manrope, sans-serif; letter-spacing: -.055em; }
        .cp-intro h1 em { color: var(--cp-teal); font-style: normal; }
        .cp-lede { max-width: 488px; margin: 0; color: #63706e; font-size: 15px; line-height: 1.75; }
        .cp-hero-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 20px; margin-top: 29px; }
        .cp-primary { min-height: 48px; display: inline-flex; align-items: center; justify-content: center; gap: 15px; padding: 0 18px; color: #fbfcf8 !important; background: var(--cp-navy); border: 1px solid var(--cp-navy); font-size: 12px; font-weight: 700; transition: background .2s ease, transform .2s ease, box-shadow .2s ease; }
        .cp-primary svg { transition: transform .2s ease; }
        .cp-primary:hover { background: #2f5967; transform: translateY(-2px); box-shadow: 0 8px 20px rgba(29, 53, 67, .14); }
        .cp-primary:hover svg { transform: translateX(3px); }
        .cp-primary:focus-visible, .cp-secondary:focus-visible, .cp-header-link:focus-visible, .cp-nav a:focus-visible { outline: 2px solid var(--cp-ochre); outline-offset: 4px; }
        .cp-secondary { display: inline-flex; align-items: center; gap: 6px; color: #506260; font-size: 11px; font-weight: 700; transition: color .2s ease; }
        .cp-secondary:hover { color: var(--cp-teal); }
        .cp-secondary svg { transition: transform .2s ease; }
        .cp-secondary:hover svg { transform: translate(2px, 2px); }
        .cp-trust-line { display: flex; align-items: center; gap: 12px; margin-top: 31px; color: #737e79; font-size: 10px; line-height: 1.5; }
        .cp-trust-line strong { color: #354b50; font-size: 10px; font-weight: 700; }
        .cp-trust-icon { width: 32px; height: 32px; display: grid; place-items: center; color: var(--cp-teal); border: 1px solid #cdd8cf; border-radius: 50%; }
        .cp-preview-wrap { position: relative; padding: 17px 0 0 17px; }
        .cp-preview-wrap::before { position: absolute; content: ""; z-index: 0; inset: 0 17px 28px 0; border: 1px solid rgba(56, 108, 102, .25); }
        .cp-preview-topline { position: relative; z-index: 1; display: flex; justify-content: space-between; align-items: center; padding: 0 2px 12px 9px; }
        .cp-preview-caption, .cp-preview-state { font: 500 8px/1.2 "DM Mono", monospace; letter-spacing: .12em; }
        .cp-preview-caption { color: #62716d; }
        .cp-preview-state { display: inline-flex; align-items: center; gap: 7px; color: #857451; font-size: 7px; letter-spacing: .08em; }
        .cp-preview-state span { width: 5px; height: 5px; border-radius: 50%; background: var(--cp-ochre); }
        .cp-workspace { position: relative; z-index: 1; display: flex; min-height: 372px; background: var(--cp-white); border: 1px solid #dce1db; box-shadow: 0 20px 42px rgba(31, 52, 53, .09); }
        .cp-workspace-rail { width: 48px; flex: 0 0 48px; display: flex; flex-direction: column; align-items: center; gap: 16px; padding: 15px 0; background: #eef1eb; border-right: 1px solid #e0e4dc; color: #82908a; }
        .cp-rail-logo { width: 22px; height: 22px; display: grid; place-items: center; margin-bottom: 8px; color: #f7f7ef; background: var(--cp-navy); font: 700 11px/1 Manrope, sans-serif; }
        .cp-rail-active { width: 29px; height: 29px; display: grid; place-items: center; color: var(--cp-teal); background: #dfe9df; }
        .cp-workspace-main { flex: 1; min-width: 0; padding: 23px 23px 17px; }
        .cp-ws-heading { display: flex; align-items: flex-start; justify-content: space-between; padding-bottom: 16px; border-bottom: 1px solid #e8ebe5; }
        .cp-ws-overline { color: #8b968d; font: 500 7px/1.2 "DM Mono", monospace; letter-spacing: .15em; }
        .cp-ws-heading h2 { margin: 5px 0 0; color: #293c47; font: 700 17px/1.2 Manrope, sans-serif; letter-spacing: -.025em; }
        .cp-ws-date { color: #8c9690; font: 400 8px/1.3 "DM Mono", monospace; }
        .cp-workflow { margin-top: 17px; }
        .cp-workflow-step { display: flex; align-items: center; gap: 10px; min-height: 42px; }
        .cp-step-icon { width: 29px; height: 29px; display: grid; place-items: center; flex: 0 0 29px; color: var(--cp-teal); background: #e7eee6; }
        .cp-step-icon-sand { color: #917140; background: #f2ede1; }
        .cp-step-icon-outline { color: #617479; background: transparent; border: 1px solid #d9e0dc; }
        .cp-step-copy { display: flex; flex-direction: column; gap: 3px; }
        .cp-step-copy b { color: #35464c; font-size: 9px; font-weight: 700; }
        .cp-step-copy small { color: #909a94; font-size: 8px; }
        .cp-step-mark { margin-left: auto; color: #a2aaa2; font: 400 8px/1 "DM Mono", monospace; }
        .cp-flow-rule { height: 10px; margin-left: 14px; border-left: 1px solid #d7dfd7; }
        .cp-ws-bottom { display: grid; grid-template-columns: 1.35fr .75fr; gap: 13px; margin-top: 19px; }
        .cp-record, .cp-index { min-height: 89px; padding: 12px; background: #f5f6f1; border: 1px solid #e7eae3; }
        .cp-record-label, .cp-index-label { display: block; margin-bottom: 10px; color: #8c968d; font: 500 6px/1.2 "DM Mono", monospace; letter-spacing: .09em; }
        .cp-record-row { display: flex; align-items: center; justify-content: space-between; gap: 7px; margin-top: 7px; color: #7d8881; font-size: 7px; }
        .cp-record-row b { color: #4c5c5d; font-size: 7px; font-weight: 600; }
        .cp-record-row i { display: inline-flex; align-items: center; gap: 5px; color: #9a7a47; font-size: 7px; font-style: normal; }
        .cp-record-row i span { width: 5px; height: 5px; border-radius: 50%; background: #b8975d; }
        .cp-index-lines { height: 28px; display: flex; align-items: flex-end; gap: 3px; }
        .cp-index-lines i { display: block; width: 4px; background: #83a29a; opacity: .65; }
        .cp-index-lines i:nth-child(3n) { height: 19px; }
        .cp-index-lines i:nth-child(3n + 1) { height: 11px; }
        .cp-index-lines i:nth-child(3n + 2) { height: 24px; }
        .cp-index-foot { display: block; margin-top: 5px; color: #89938c; font-size: 7px; }
        .cp-preview-footnote { position: relative; z-index: 1; margin: 9px 0 0 9px; color: #8c9690; font-size: 8px; }
        .cp-preview-stamp { position: absolute; z-index: 2; right: -5px; bottom: 44px; width: 56px; height: 56px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px; color: #647a70; background: #e8ece3; border: 1px solid #d5ddd2; border-radius: 50%; transform: rotate(9deg); }
        .cp-preview-stamp span { font: 500 5px/1 "DM Mono", monospace; letter-spacing: .08em; }
        .cp-preview-stamp b { font: 600 14px/1 Manrope, sans-serif; }
        .cp-method { display: grid; grid-template-columns: .95fr 1.05fr; gap: 74px; padding: 27px 3px 32px; border-top: 1px solid rgba(32, 60, 83, .16); }
        .cp-section-number { display: flex; align-items: center; gap: 9px; color: #8c7957; font: 500 8px/1.4 "DM Mono", monospace; letter-spacing: .11em; }
        .cp-section-number i { width: 20px; height: 1px; background: #bca478; }
        .cp-method-intro h2 { margin: 13px 0 0; color: var(--cp-ink); font: 700 23px/1.2 Manrope, sans-serif; letter-spacing: -.035em; }
        .cp-method-copy > p { max-width: 488px; margin: 0 0 18px; color: #67736e; font-size: 11px; line-height: 1.65; }
        .cp-capabilities { display: flex; flex-wrap: wrap; gap: 8px 18px; }
        .cp-capabilities span { display: inline-flex; align-items: center; gap: 7px; color: #495b59; font-size: 9px; white-space: nowrap; }
        .cp-capabilities b { display: grid; place-items: center; width: 16px; height: 16px; color: #55766c; background: #e4ebe3; font: 500 7px/1 "DM Mono", monospace; }
        .cp-footer { display: flex; justify-content: space-between; gap: 20px; padding: 18px 3px 22px; border-top: 1px solid rgba(32, 60, 83, .14); color: #89918a; font: 500 7px/1.4 "DM Mono", monospace; letter-spacing: .06em; }
        .cp-footer i { padding: 0 5px; color: #b19a72; font-style: normal; }
        @media (min-width: 1400px) { .cp-shell { width: min(1200px, calc(100% - 100px)); } }
        @media (max-width: 900px) {
          .cp-shell { width: min(720px, calc(100% - 48px)); }
          .cp-header { min-height: 78px; }
          .cp-nav { margin-left: 32px; gap: 20px; }
          .cp-hero { grid-template-columns: 1fr; gap: 44px; padding: 56px 0 50px; }
          .cp-intro { max-width: 610px; }
          .cp-preview-wrap { width: min(560px, 100%); justify-self: center; }
          .cp-method { gap: 34px; }
        }
        @media (max-width: 600px) {
          .cti-professional { min-height: 100dvh; }
          .cp-shell { width: calc(100% - 40px); }
          .cp-header { min-height: 72px; }
          .cp-brand { width: 113px; height: 40px; }
          .cp-brand img { width: 138px; }
          .cp-nav, .cp-access-label { display: none; }
          .cp-header-right { gap: 0; }
          .cp-header-link { font-size: 11px; }
          .cp-hero { gap: 34px; padding: 47px 0 39px; }
          .cp-kicker { font-size: 7px; letter-spacing: .1em; }
          .cp-kicker-mark { width: 13px; margin-right: 7px; }
          .cp-kicker-divider { margin: 0 6px; }
          .cp-intro h1 { margin: 20px 0 16px; font-size: clamp(39px, 11vw, 52px); }
          .cp-lede { font-size: 14px; line-height: 1.68; }
          .cp-hero-actions { align-items: flex-start; flex-direction: column; gap: 16px; margin-top: 23px; }
          .cp-primary { min-height: 47px; }
          .cp-trust-line { margin-top: 24px; }
          .cp-preview-wrap { padding: 12px 0 0 12px; }
          .cp-preview-wrap::before { inset: 0 12px 25px 0; }
          .cp-workspace { min-height: 0; }
          .cp-workspace-rail { width: 38px; flex-basis: 38px; gap: 13px; padding-top: 12px; }
          .cp-workspace-main { padding: 17px 13px 13px; }
          .cp-ws-heading h2 { font-size: 15px; }
          .cp-ws-date { font-size: 7px; }
          .cp-workflow { margin-top: 13px; }
          .cp-workflow-step { min-height: 39px; gap: 8px; }
          .cp-step-copy b { font-size: 8px; }
          .cp-step-copy small { font-size: 7px; }
          .cp-ws-bottom { grid-template-columns: 1.2fr .8fr; gap: 7px; margin-top: 14px; }
          .cp-record, .cp-index { min-height: 82px; padding: 9px; }
          .cp-record-row { align-items: flex-start; flex-direction: column; gap: 3px; }
          .cp-preview-stamp { right: -8px; bottom: 42px; width: 46px; height: 46px; }
          .cp-method { grid-template-columns: 1fr; gap: 19px; padding: 22px 3px 25px; }
          .cp-method-intro h2 { font-size: 22px; }
          .cp-method-copy > p { margin-bottom: 13px; }
          .cp-capabilities { gap: 8px 13px; }
          .cp-capabilities span { font-size: 8px; }
          .cp-footer { flex-direction: column; gap: 7px; padding: 15px 3px 20px; font-size: 6px; }
        }
        @media (prefers-reduced-motion: reduce) {
          .cti-professional *, .cti-professional *::before, .cti-professional *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; }
        }
      `}</style>
    </main>
  );
}
