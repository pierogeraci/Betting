import ExcelJS from "exceljs";
import {
  ctiActivityTable,
  ctiBettorsTable,
  ctiEntitiesTable,
  ctiEventsTable,
  ctiEvidenceTable,
  ctiSitesTable,
  ctiSourcesTable,
  ctiTrustScoresTable,
} from "@workspace/db";
import {
  trustCalibrationNotice,
  trustFactorDefinitions,
} from "./cti-utils";

export type WorkbookScope =
  | "all"
  | "sources"
  | "evidence"
  | "sites"
  | "entities"
  | "events"
  | "bettors"
  | "trust"
  | "audit";

export interface WorkbookData {
  sources: (typeof ctiSourcesTable.$inferSelect)[];
  evidence: (typeof ctiEvidenceTable.$inferSelect)[];
  sites: (typeof ctiSitesTable.$inferSelect)[];
  entities: (typeof ctiEntitiesTable.$inferSelect)[];
  events: (typeof ctiEventsTable.$inferSelect)[];
  scores: (typeof ctiTrustScoresTable.$inferSelect)[];
  activity: (typeof ctiActivityTable.$inferSelect)[];
  bettors: (typeof ctiBettorsTable.$inferSelect)[];
}

function safeCell(value: unknown) {
  if (value == null) return "";
  if (value instanceof Date) return value.toISOString();
  if (typeof value === "object") {
    const json = JSON.stringify(value);
    return /^[=+\-@]/.test(json) ? `'${json}` : json;
  }
  if (typeof value === "string" && /^[=+\-@]/.test(value)) return `'${value}`;
  return value;
}

function addSheet(
  workbook: ExcelJS.Workbook,
  name: string,
  headers: string[],
  rows: unknown[][],
) {
  const sheet = workbook.addWorksheet(name);
  sheet.addRow(headers);
  for (const row of rows) sheet.addRow(row.map(safeCell));
  sheet.views = [{ state: "frozen", ySplit: 1 }];
  sheet.autoFilter = {
    from: { row: 1, column: 1 },
    to: { row: 1, column: Math.max(headers.length, 1) },
  };
  sheet.getRow(1).font = { bold: true };
  sheet.columns.forEach((column, index) => {
    const values = sheet.getColumn(index + 1).values.slice(1, 18);
    column.width = Math.min(
      Math.max(14, ...values.map((value) => String(value ?? "").length + 2)),
      48,
    );
  });
}

function localizedEnum(value: string | null | undefined): string | null | undefined {
  if (value == null) return value;
  const labels: Record<string, string> = {
    low: "basso", medium: "medio", high: "alto", unassessed: "non valutato",
    draft: "bozza", in_review: "in revisione", approved: "approvato", rejected: "respinto",
    expired: "scaduto", revoked: "revocato", suspended: "sospeso", not_configured: "non configurato",
    connected: "connesso", error: "errore", off: "disattivato", new: "nuovo", classified: "classificato",
    normalized: "normalizzato", reviewed: "revisionato", archived: "archiviato", company: "società",
    person: "persona", unknown: "sconosciuto", evidence: "evidenza", source: "fonte",
    site: "sito", event: "evento", entity: "entità", bettor: "scommettitore", web: "web",
    document: "documento", email: "e-mail", operator_provided: "fornito dall’operatore",
    regulatory_filing: "atto normativo", regulatory: "normativa", sports: "sport",
    operator: "operatore", market_data: "dati di mercato", other: "altro", manual: "manuale",
    admin: "amministratore", analyst: "analista", compliance_reviewer: "revisore della conformità",
    restricted_analyst: "analista con accesso limitato", read_only: "sola lettura",
  };
  return labels[value] ?? value;
}

function localizeActivity(action: string): string {
  const labels: Record<string, string> = {
    "Captured evidence": "Evidenza acquisita",
    "Updated evidence record": "Record di evidenza aggiornato",
    "Classified and normalized evidence": "Evidenza classificata e normalizzata",
    "Created betting-site profile": "Profilo del sito creato",
    "Updated betting-site profile": "Profilo del sito aggiornato",
    "Created legal-entity candidate": "Entità legale candidata creata",
    "Registered sports event": "Evento sportivo registrato",
    "Updated event data": "Dati dell’evento aggiornati",
    "Added pseudonymous bettor profile": "Profilo pseudonimo dello scommettitore aggiunto",
    "Registered source for review": "Fonte registrata per la revisione",
    "Updated source authorization record": "Dati di autorizzazione della fonte aggiornati",
  };
  if (labels[action]) return labels[action];
  if (action.startsWith("Rated event ")) return `Evento valutato: ${localizedEnum(action.slice(12))}`;
  if (action.startsWith("Calculated Trust Index ")) return `Indice di affidabilità calcolato: ${localizedEnum(action.slice(23))}`;
  if (action.startsWith("Source authorization ")) return `Autorizzazione della fonte: ${action.slice(21)}`;
  if (action.startsWith("Entity association ")) return `Collegamento all’entità: ${action.slice(19)}`;
  return action;
}

export async function createWorkbook(
  scope: WorkbookScope,
  includeRestricted: boolean,
  data: WorkbookData,
  generatedAt = new Date().toISOString(),
): Promise<Buffer> {
  const restrictedProfilesIncluded =
    includeRestricted && (scope === "all" || scope === "bettors");
  const workbook = new ExcelJS.Workbook();
  workbook.created = new Date(generatedAt);
  workbook.creator = "CTI Intelligence";
  workbook.subject = "Estrazione di intelligence da fonti autorizzate";
  workbook.title = "Quaderno di lavoro CTI";

  addSheet(workbook, "Riepilogo", ["Campo", "Valore"], [
    ["Generato il", generatedAt],
    ["Ambito richiesto", ({
      all: "tutti i dati", sources: "fonti", evidence: "evidenze", sites: "siti",
      entities: "entità", events: "eventi sportivi", bettors: "profili degli scommettitori",
      trust: "indice di affidabilità", audit: "registro attività",
    } as Record<string, string>)[scope] || scope],
    ["Profili riservati inclusi", restrictedProfilesIncluded ? "Sì" : "No"],
    ["Fonti", data.sources.length],
    ["Record di evidenza", data.evidence.length],
    ["Siti di scommesse", data.sites.length],
    ["Entità legali", data.entities.length],
    ["Eventi sportivi", data.events.length],
    ["Calcoli dell’Indice di affidabilità", data.scores.length],
    ["Profili scommettitori", restrictedProfilesIncluded ? data.bettors.length : "Non inclusi (riservati)"],
    ["Regola sui dati", "Inserimento manuale e sole fonti autorizzate; le credenziali non vengono mai esportate."],
    ["Stato dei punteggi", "Provvisori; da validare e calibrare prima dell’uso operativo."],
  ]);

  const requestedSheets = (key: string) => scope === "all" || scope === key;
  if (requestedSheets("sources")) {
    addSheet(workbook, "Fonti", [
      "ID", "Nome", "Fornitore", "URL", "Categoria", "Metodo di accesso", "Titolare",
      "Finalità", "Ambito", "Categorie dei dati", "Base dell’autorizzazione",
      "Prova dell’autorizzazione", "Valida dal", "Valida fino al", "Ruolo del revisore",
      "Stato legale", "Stato del connettore", "Ambiti del connettore", "Nota della revisione",
    ], data.sources.map((row) => [
      row.id, row.name, row.provider, row.url, localizedEnum(row.category), localizedEnum(row.accessMethod),
      row.owner, row.purpose, row.scope, row.dataCategories,
      row.authorizationBasis, row.authorizationEvidenceName, row.validFrom,
      row.validUntil, localizedEnum(row.reviewerRole), localizedEnum(row.legalStatus), localizedEnum(row.connectorStatus),
      row.connectorScopes, row.reviewNote,
    ]));
  }
  if (requestedSheets("evidence")) {
    addSheet(workbook, "Evidenze", [
      "ID", "Titolo", "Canale", "ID fonte", "URL originale", "Acquisita il",
      "Contenuto originale", "Categorie", "Fatti estratti", "Campi normalizzati",
      "Note di arricchimento", "Stato", "ID sito", "ID evento", "ID entità",
      "Allegato", "Sintetico",
    ], data.evidence.map((row) => [
      row.id, row.title, localizedEnum(row.channel), row.sourceId, row.originalUrl,
      row.capturedAt, row.rawContent, row.categories, row.extractedFacts,
      row.normalizedFields, row.enrichmentNotes, localizedEnum(row.status), row.relatedSiteId,
      row.eventId, row.entityId, row.attachmentName, row.synthetic,
    ]));
  }
  if (requestedSheets("sites")) {
    addSheet(workbook, "Siti", [
      "ID", "Dominio", "Nome", "Descrizione", "Rilevato per la prima volta", "Ultima rilevazione",
      "Giurisdizione", "Licenza dichiarata", "ID entità legale", "Stato collegamento entità",
      "Fascia di rischio", "Indice di affidabilità",
    ], data.sites.map((row) => [
      row.id, row.domain, row.name, row.description, row.firstSeenAt,
      row.lastSeenAt, row.jurisdiction, row.licenseClaim, row.legalEntityId,
      localizedEnum(row.entityLinkStatus), localizedEnum(row.riskBand), row.trustIndex,
    ]));
  }
  if (requestedSheets("entities")) {
    addSheet(workbook, "Entità", [
      "ID", "Nome", "Tipo", "Paese", "ID di registrazione", "Note sulle evidenze",
    ], data.entities.map((row) => [
      row.id, row.name, localizedEnum(row.entityType), row.country, row.registrationId,
      row.evidenceNotes,
    ]));
  }
  if (requestedSheets("events")) {
    addSheet(workbook, "Eventi sportivi", [
      "ID", "Sport", "Competizione", "Casa", "Ospite", "Ora di inizio",
      "Fonti delle quote", "Volume del mercato", "Quote anomale", "Fascia di rischio evento",
      "Nota della valutazione", "Dettaglio valutazione", "Sintetico",
    ], data.events.map((row) => [
      row.id, row.sport, row.competition, row.home, row.away, row.startsAt,
      row.oddsSources, row.marketVolume, row.unusualOdds, localizedEnum(row.riskBand),
      row.ratingNote, row.ratingDetails, row.synthetic,
    ]));
  }
  if (requestedSheets("trust")) {
    addSheet(workbook, "Indice affidabilità", [
      "ID", "ID sito", "Punteggio di vulnerabilità", "Fascia di vulnerabilità",
      "Punteggio di minaccia", "Fascia di minaccia", "Vulnerabilità normalizzata",
      "Minaccia normalizzata", "Indice di affidabilità", "Fascia dell’indice", "Dettaglio fattori",
      "Dettaglio minaccia", "Nota dell’analista", "Nota sulla calibrazione", "Calcolato il",
    ], data.scores.map((row) => [
      row.id, row.siteId, row.vulnerabilityScore, localizedEnum(row.vulnerabilityBand),
      row.threatScore, localizedEnum(row.threatBand), row.normalizedVulnerability,
      row.normalizedThreat, row.trustIndex, localizedEnum(row.trustBand),
      row.factorDetails, row.threatDetails, row.analystNote,
      row.calibrationNotice, row.computedAt,
    ]));
  }
  if (requestedSheets("bettors") && restrictedProfilesIncluded) {
    addSheet(workbook, "Profili scommettitori", [
      "ID", "ID pseudonimo", "Operatore", "Inizio periodo", "Fine periodo",
      "Puntata media", "Vincite lorde", "Percentuale di vincita", "Base dei dati",
      "Sintetico", "Nota sul rischio",
    ], data.bettors.map((row) => [
      row.id, row.pseudonymousId, row.operator, row.periodStart, row.periodEnd,
      row.averageBet, row.grossWinnings, row.winRate, row.dataBasis,
      row.synthetic, row.riskNote,
    ]));
  }
  if (requestedSheets("audit")) {
    addSheet(workbook, "Registro attività", [
      "ID", "Azione", "Tipo di entità", "ID entità", "Descrizione entità",
      "Operatore", "Data di registrazione",
    ], data.activity.map((row) => [
      row.id, localizeActivity(row.action), localizedEnum(row.entityType), row.entityId, row.entityLabel,
      "Operatore anonimo", row.createdAt,
    ]));
  }
  if (scope === "all" || scope === "trust" || scope === "events") {
    addSheet(workbook, "Metodologia", ["Voce", "Definizione"], [
      ["Punteggio di vulnerabilità", "Somma degli indicatori binari moltiplicati per i pesi del prototipo approvati; intervallo 0–20."],
      ...trustFactorDefinitions.map((factor) => [factor.label, `Peso ${factor.weight}`]),
      ["Fasce di vulnerabilità", "Basso < 6; medio >= 6 e < 12; alto >= 12."],
      ["Punteggio di minaccia", "Somma di tre livelli da 1 a 3; intervallo 3–9."],
      ["Puntata media", "Basso < €50; medio >= €50 e < €250; alto >= €250."],
      ["Vincite lorde", "Basso < €1.000; medio >= €1.000 e < €5.000; alto >= €5.000."],
      ["Percentuale di vincita", "Basso < 25%; medio >= 25% e < 50%; alto >= 50%."],
      ["Indice di affidabilità", "Media tra (punteggio di vulnerabilità/20*100) e ((punteggio di minaccia-3)/6*100)."],
      ["Fasce dell’indice", "Basso < 33; medio >= 33 e < 67; alto >= 67."],
      ["Valutazione dell’evento", "Euristica provvisoria separata: meno di 3 fonti delle quote aggiunge 1; quote anomale aggiungono 2; volume >= €10.000 aggiunge 1 e >= €50.000 aggiunge 2. Basso 0–1; medio 2–3; alto >= 4."],
      ["Limiti della valutazione evento", "Regola di prototipo, non probabilità di frode validata; richiede calibrazione su dati storici autorizzati."],
      ["Calibrazione", trustCalibrationNotice],
      ["Autorizzazione della fonte", "La registrazione o revisione di una fonte non costituisce parere legale né autorizzazione all’accesso."],
      ["Riservatezza", "Non sono inclusi valori delle credenziali né identificativi diretti degli scommettitori."],
    ]);
  }

  const buffer = await workbook.xlsx.writeBuffer();
  return Buffer.from(buffer);
}
