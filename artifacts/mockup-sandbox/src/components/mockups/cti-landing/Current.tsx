import { ArrowRight } from "lucide-react";
import "./_group.css";

export function Current() {
  return (
    <main className="cti-current">
      <a className="auth-brand" href="#" aria-label="Softstrategy">
        <img src="/__mockup/softstrategy-logo.svg" alt="Softstrategy" />
      </a>
      <div className="auth-landing-content">
        <div className="eyebrow">PIATTAFORMA DI ANALISI CTI</div>
        <h1>
          Analisi autorizzata.
          <br />
          Evidenze tracciabili.
        </h1>
        <p className="auth-description">
          Una piattaforma per registrare fonti autorizzate, conservare le evidenze e verificare
          valutazioni ed esportazioni.
        </p>
        <div className="auth-landing-actions">
          <a className="btn" href="/sign-in">
            Accedi alla piattaforma <ArrowRight size={16} aria-hidden="true" />
          </a>
        </div>
        <p className="auth-landing-note">
          Accesso locale con ID utente e password. Gli account sono configurati dall’amministratore.
        </p>
      </div>
    </main>
  );
}
