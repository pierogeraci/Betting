/**
 * Schema relazionale del portale Python.
 *
 * Le definizioni sono ricavate dal modello SQLAlchemy della versione Git.
 * Sono tabelle nuove nello stesso database PostgreSQL: non sostituiscono né
 * rinominano le tabelle cti_* già gestite da Replit Publish.
 */
import { sql } from "drizzle-orm";
import {
  bigserial,
  bigint,
  boolean,
  check,
  index,
  integer,
  jsonb,
  numeric,
  pgTable,
  serial,
  text,
  timestamp,
  uniqueIndex,
  varchar,
  type AnyPgColumn,
} from "drizzle-orm/pg-core";

type ForeignKeySpec = [string, string, string];
type ColumnSpec = [string, string, ForeignKeySpec | []];
type UniqueSpec = [string, string[]];
type CheckSpec = [string, string];
type IndexSpec = [string, boolean, string[]];
type TableSpec = [string, ColumnSpec[], UniqueSpec[], CheckSpec[], IndexSpec[]];

const definitions: TableSpec[] = [
  ["emoji",[["id","si",[]],["carattere","v16",[]],["piattaforma","v20",[]],["significato","v200",[]],["categoria","v40",[]],["occorrenze","i",[]]],[["emoji_unica",["carattere","piattaforma"]]],[],[]],
  ["entita",[["id","sbi",[]],["tipo","v30",[]],["valore","t",[]],["creato_il","tsz",[]]],[["entita_tipo_valore",["tipo","valore"]]],[],[]],
  ["sito",[["id","sbi",[]],["dominio","v255",[]],["gruppo","i?",[]],["esito_adm","v30",[]],["fonte_scoperta","v40?",[]],["primo_avvistamento","tsz",[]],["ultimo_snapshot_il","tsz?",[]],["creato_il","tsz",[]]],[["",["dominio"]]],[],[["ix_sito_gruppo",false,["gruppo"]],["ix_sito_esito_adm",false,["esito_adm"]]]],
  ["sonda",[["id","si",[]],["nome","v80",[]],["tipo","v20",[]],["configurazione","j",[]],["cursore","j",[]],["stato","v20",[]],["ultima_esecuzione","tsz?",[]],["ultimo_errore","t?",[]],["disponibile_dal","tsz?",[]],["creato_il","tsz",[]]],[["",["nome"]]],[],[]],
  ["utente",[["id","si",[]],["nome_utente","v64",[]],["nome","v120",[]],["password_hash","v255",[]],["ruolo","v20",[]],["attivo","b",[]],["tentativi_falliti","i",[]],["bloccato_fino_a","tsz?",[]],["creato_il","tsz",[]]],[["",["nome_utente"]]],[["utente_ruolo","ruolo in ('analista','amministratore')"]],[]],
  ["valutazione",[["id","si",[]],["ambito","v40",[]],["versione","v80",[]],["esempi","i",[]],["misure","j",[]],["errori","j",[]],["eseguita_il","tsz",[]]],[],[],[]],
  ["elemento_grezzo",[["id","sbi",[]],["sonda_id","i?",["sonda","id",""]],["fonte","v40",[]],["tipo","v20",[]],["riferimento","t",[]],["contenuto","t?",[]],["oggetto_chiave","v200?",[]],["sha256","v64",[]],["raccolto_il","tsz",[]],["inserito_da","i?",["utente","id",""]],["metadati","j",[]]],[["elemento_grezzo_fonte_sha256",["fonte","sha256"]]],[],[["ix_elemento_grezzo_fonte",false,["fonte"]],["ix_elemento_grezzo_raccolto_il",false,["raccolto_il"]]]],
  ["lavoro",[["id","sbi",[]],["coda","v20",[]],["tipo","v40",[]],["carico","j",[]],["stato","v20",[]],["tentativi","i",[]],["max_tentativi","i",[]],["disponibile_dal","tsz",[]],["preso_da","v80?",[]],["preso_il","tsz?",[]],["scade_il","tsz?",[]],["risultato","j",[]],["errore","t?",[]],["successivo","v40?",[]],["origine_id","bi?",[]],["sito_id","bi?",["sito","id","set null"]],["creato_da","i?",["utente","id",""]],["creato_il","tsz",[]],["chiuso_il","tsz?",[]]],[],[["lavoro_stato","stato in ('in_attesa','in_corso','completato','fallito')"],["lavoro_coda","coda in ('raccolta','interna')"]],[["lavoro_da_prendere",false,["coda","stato","disponibile_dal"]],["ix_lavoro_sito_id",false,["sito_id"]]]],
  ["legame_entita",[["id","sbi",[]],["da_entita_id","bi",["entita","id","cascade"]],["a_entita_id","bi",["entita","id","cascade"]],["tipo","v40",[]],["evidenza","j",[]],["creato_il","tsz",[]]],[["legame_unico",["da_entita_id","a_entita_id","tipo"]]],[],[["ix_legame_entita_a_entita_id",false,["a_entita_id"]],["ix_legame_entita_da_entita_id",false,["da_entita_id"]]]],
  ["legame_sito",[["id","sbi",[]],["sito_a","bi",["sito","id","cascade"]],["sito_b","bi",["sito","id","cascade"]],["motivo","v40",[]],["valore","t",[]],["forza","n4_3",[]],["creato_il","tsz",[]]],[["legame_sito_unico",["sito_a","sito_b","motivo","valore"]]],[],[["ix_legame_sito_sito_b",false,["sito_b"]],["ix_legame_sito_sito_a",false,["sito_a"]]]],
  ["modello",[["id","si",[]],["nome","v40",[]],["versione","v80",[]],["chiave","v200?",[]],["metriche","j",[]],["attivo","b",[]],["addestrato_il","tsz",[]],["addestrato_da","i?",["utente","id",""]]],[],[],[["ix_modello_nome",false,["nome"]]]],
  ["parola_chiave",[["id","si",[]],["termine","v120",[]],["categoria","v40",[]],["lingua","v10",[]],["attiva","b",[]],["avviso","b",[]],["creato_da","i?",["utente","id",""]],["creato_il","tsz",[]]],[["parola_chiave_unica",["termine"]]],[],[]],
  ["punteggio",[["id","sbi",[]],["sito_id","bi",["sito","id","cascade"]],["ambito","v80",[]],["vulnerabilita","n6_2?",[]],["livello_vulnerabilita","v10?",[]],["minaccia","n6_2?",[]],["livello_minaccia","v10?",[]],["trust_index","n6_2?",[]],["classe_rischio","v10?",[]],["copertura","n4_3",[]],["versione_regole","v40",[]],["dettaglio","j",[]],["calcolato_il","tsz",[]]],[],[],[["ix_punteggio_sito_id",false,["sito_id"]]]],
  ["sessione_utente",[["token_hash","v64#",[]],["utente_id","i",["utente","id","cascade"]],["csrf","v64",[]],["creata_il","tsz",[]],["scade_il","tsz",[]]],[],[],[["ix_sessione_utente_utente_id",false,["utente_id"]]]],
  ["snapshot",[["id","sbi",[]],["sito_id","bi",["sito","id","cascade"]],["lavoro_id","bi?",[]],["stato","v20",[]],["motivo","v60?",[]],["errore","t?",[]],["url_richiesto","t",[]],["url_finale","t?",[]],["dominio_finale","v255?",[]],["codice_http","i?",[]],["titolo","t?",[]],["reindirizzamenti","j",[]],["html_sha256","v64?",[]],["html_chiave","v200?",[]],["schermata_sha256","v64?",[]],["schermata_chiave","v200?",[]],["traffico_sha256","v64?",[]],["traffico_chiave","v200?",[]],["sha256","v64",[]],["raccolto_il","tsz",[]],["strumento","v60",[]],["versione_strumento","v60",[]],["metadati","j",[]]],[["",["lavoro_id"]]],[["snapshot_stato","stato in ('riuscito','bloccato','errore')"]],[["ix_snapshot_sito_id",false,["sito_id"]],["ix_snapshot_raccolto_il",false,["raccolto_il"]]]],
  ["adm_caricamento",[["id","si",[]],["elenco","v20",[]],["versione","i",[]],["stato","v20",[]],["fonte_url","t?",[]],["nome_file","v255",[]],["sha256","v64",[]],["elemento_grezzo_id","bi?",["elemento_grezzo","id",""]],["righe_totali","i",[]],["righe_valide","i",[]],["righe_scartate","i",[]],["caricato_il","tsz",[]],["verificato_il","tsz",[]],["caricato_da","i?",["utente","id",""]],["note","t",[]]],[["adm_caricamento_versione",["elenco","versione"]]],[["adm_elenco","elenco in ('concessionari','siti_inibiti')"],["adm_stato","stato in ('attivo','sostituito')"]],[]],
  ["canale",[["id","sbi",[]],["piattaforma","v20",[]],["identificativo","v120",[]],["titolo","v300",[]],["tipo","v20?",[]],["stato","v20",[]],["partecipanti","i?",[]],["cursore","bi",[]],["scoperto_da","bi?",["elemento_grezzo","id","set null"]],["motivo","t",[]],["ultimo_controllo","tsz?",[]],["ultimo_errore","t?",[]],["approvato_da","i?",["utente","id",""]],["creato_il","tsz",[]]],[["canale_unico",["piattaforma","identificativo"]]],[["canale_stato","stato in ('da_approvare','attivo','in_pausa','rifiutato','in_errore')"]],[["ix_canale_stato",false,["stato"]]]],
  ["etichetta",[["id","sbi",[]],["elemento_grezzo_id","bi",["elemento_grezzo","id","cascade"]],["pubblicita_gioco","b?",[]],["entita","j",[]],["note","t",[]],["utente_id","i?",["utente","id",""]],["creato_il","tsz",[]],["aggiornato_il","tsz",[]]],[["",["elemento_grezzo_id"]]],[],[]],
  ["evento_sportivo",[["id","sbi",[]],["nome","v300",[]],["sport","v60",[]],["competizione","v200",[]],["inizio","tsz?",[]],["rating","v10?",[]],["dettaglio","j",[]],["elemento_grezzo_id","bi?",["elemento_grezzo","id","set null"]],["creato_il","tsz",[]]],[["evento_unico",["nome","inizio"]]],[],[]],
  ["indicatore",[["id","sbi",[]],["sito_id","bi",["sito","id","cascade"]],["snapshot_id","bi?",["snapshot","id","set null"]],["codice","v60",[]],["valore","v20",[]],["evidenza","j",[]],["certezza","n4_3",[]],["collettore","v60",[]],["versione_collettore","v20",[]],["rilevato_il","tsz",[]]],[],[["indicatore_certezza","certezza >= 0 and certezza <= 1"],["indicatore_valore","valore in ('presente','assente','non_determinabile')"]],[["indicatore_sito_codice",false,["sito_id","codice","rilevato_il"]]]],
  ["media",[["id","sbi",[]],["elemento_grezzo_id","bi",["elemento_grezzo","id","cascade"]],["tipo","v20",[]],["mime","v120",[]],["nome_file","v255",[]],["dimensione","bi",[]],["sha256","v64",[]],["oggetto_chiave","v200",[]],["creato_il","tsz",[]]],[["media_elemento_sha256",["elemento_grezzo_id","sha256"]]],[],[["ix_media_sha256",false,["sha256"]]]],
  ["puntata",[["id","sbi",[]],["sito_id","bi",["sito","id","cascade"]],["tipo_gioco","v40?",[]],["importo_puntato","n14_4",[]],["importo_vinto","n14_4",[]],["valuta","v10",[]],["momento","tsz?",[]],["fonte","v20",[]],["elemento_grezzo_id","bi?",["elemento_grezzo","id","set null"]],["snapshot_id","bi?",["snapshot","id","set null"]],["creato_il","tsz",[]]],[],[["puntata_fonte","fonte in ('osservata','caricata')"]],[["ix_puntata_sito_id",false,["sito_id"]]]],
  ["registro_voce",[["id","sbi",[]],["registro","v20",[]],["fonte","v200",[]],["nome","v300",[]],["nome_normalizzato","v300",[]],["paese","v60",[]],["numero","v80",[]],["stato","v60",[]],["dettagli","j",[]],["elemento_grezzo_id","bi?",["elemento_grezzo","id","set null"]],["creato_il","tsz",[]]],[],[["registro_tipo","registro in ('societa','licenze')"]],[["ix_registro_voce_registro",false,["registro"]],["ix_registro_voce_nome_normalizzato",false,["nome_normalizzato"]],["ix_registro_voce_numero",false,["numero"]]]],
  ["revisione",[["id","sbi",[]],["tipo","v30",[]],["stato","v20",[]],["sito_id","bi?",["sito","id","cascade"]],["snapshot_id","bi?",["snapshot","id","set null"]],["elemento_grezzo_id","bi?",["elemento_grezzo","id","set null"]],["motivo","t",[]],["assegnata_a","i?",["utente","id",""]],["esito","v40?",[]],["giudizio","j",[]],["note","t",[]],["creata_il","tsz",[]],["chiusa_il","tsz?",[]],["chiusa_da","i?",["utente","id",""]]],[],[["revisione_stato","stato in ('aperta','in_carico','chiusa')"]],[["ix_revisione_tipo",false,["tipo"]],["ix_revisione_stato",false,["stato"]]]],
  ["adm_concessionario",[["id","sbi",[]],["caricamento_id","i",["adm_caricamento","id","cascade"]],["numero_concessione","v40",[]],["ragione_sociale","t",[]],["dominio","v255",[]],["dominio_registrabile","v255",[]],["riga","i",[]],["riga_originale","t",[]]],[],[],[["adm_conc_registrabile",false,["caricamento_id","dominio_registrabile"]],["adm_conc_dominio",false,["caricamento_id","dominio"]]]],
  ["adm_sito_inibito",[["id","sbi",[]],["caricamento_id","i",["adm_caricamento","id","cascade"]],["dominio","v255",[]],["dominio_registrabile","v255",[]],["riga","i",[]],["riga_originale","t",[]]],[],[],[["adm_inib_dominio",false,["caricamento_id","dominio"]],["adm_inib_registrabile",false,["caricamento_id","dominio_registrabile"]]]],
  ["avviso",[["id","sbi",[]],["tipo","v40",[]],["titolo","v300",[]],["testo","t",[]],["sito_id","bi?",["sito","id","cascade"]],["elemento_grezzo_id","bi?",["elemento_grezzo","id","cascade"]],["canale_id","bi?",["canale","id","set null"]],["letto","b",[]],["letto_da","i?",["utente","id",""]],["creato_il","tsz",[]]],[],[],[["ix_avviso_letto",false,["letto"]],["ix_avviso_creato_il",false,["creato_il"]]]],
  ["estrazione",[["id","sbi",[]],["elemento_grezzo_id","bi?",["elemento_grezzo","id","cascade"]],["media_id","bi?",["media","id","cascade"]],["tipo","v30",[]],["testo","t",[]],["tempo_inizio_ms","i?",[]],["tempo_fine_ms","i?",[]],["modello","v80",[]],["versione_modello","v40",[]],["metadati","j",[]],["creato_il","tsz",[]]],[],[],[]],
  ["legal_entity",[["id","sbi",[]],["sito_id","bi",["sito","id","cascade"]],["nome","v300",[]],["paese","v60",[]],["numero","v80",[]],["punteggio","n5_3",[]],["evidenze","j",[]],["registro_voce_id","bi?",["registro_voce","id","set null"]],["stato","v20",[]],["confermata_da","i?",["utente","id",""]],["note","t",[]],["creato_il","tsz",[]]],[],[["legal_entity_stato","stato in ('confermata','respinta')"]],[["ix_legal_entity_sito_id",false,["sito_id"]]]],
  ["quota_evento",[["id","sbi",[]],["evento_id","bi",["evento_sportivo","id","cascade"]],["bookmaker","v120",[]],["momento","tsz",[]],["esito","v40",[]],["quota","n10_3",[]],["volume","n16_2?",[]]],[],[],[["ix_quota_evento_evento_id",false,["evento_id"]]]],
  ["menzione_entita",[["id","sbi",[]],["entita_id","bi",["entita","id","cascade"]],["elemento_grezzo_id","bi",["elemento_grezzo","id","cascade"]],["estrazione_id","bi?",["estrazione","id","cascade"]],["creato_il","tsz",[]]],[["menzione_unica",["entita_id","elemento_grezzo_id","estrazione_id"]]],[],[["ix_menzione_entita_entita_id",false,["entita_id"]],["ix_menzione_entita_elemento_grezzo_id",false,["elemento_grezzo_id"]]]],
];

const exportedTables: Record<string, any> = {};

function creaColonna(name: string, code: string, target: ForeignKeySpec | []): any {
  const nullable = code.endsWith("?");
  const primary = code.endsWith("#");
  const type = code.replace(/[?#]$/, "");
  let column: any;

  if (type === "si") column = serial(name).primaryKey();
  else if (type === "sbi") column = bigserial(name, { mode: "number" }).primaryKey();
  else if (type === "i") column = integer(name);
  else if (type === "bi") column = bigint(name, { mode: "number" });
  else if (type === "b") column = boolean(name);
  else if (type === "t") column = text(name);
  else if (type === "j") column = jsonb(name);
  else if (type === "tsz") column = timestamp(name, { withTimezone: true });
  else if (type === "ts") column = timestamp(name, { withTimezone: false });
  else if (type.startsWith("v")) column = type === "v0" ? text(name) : varchar(name, { length: Number(type.slice(1)) });
  else if (type.startsWith("n")) {
    const [precision, scale] = type.slice(1).split("_").map(Number);
    column = numeric(name, { precision, scale });
  } else throw new Error(`Tipo Drizzle non gestito: ${type}`);

  if (!nullable && type !== "si" && type !== "sbi") column = column.notNull();
  if (primary && type !== "si" && type !== "sbi") column = column.primaryKey();
  if (target.length) {
    const [tableName, columnName, onDelete] = target;
    column = column.references(
      () => exportedTables[tableName][columnName] as AnyPgColumn,
      onDelete ? { onDelete: onDelete as "cascade" | "set null" | "restrict" | "no action" | "set default" } : undefined,
    );
  }
  return column;
}

function nomeVincolo(tableName: string, supplied: string, columns: string[]): string {
  return (supplied || `py_${tableName}_${columns.join("_")}_uq`).slice(0, 63);
}

function creaTabella(definition: TableSpec): any {
  const [name, columns, uniques, checks, indexes] = definition;
  const columnMap = Object.fromEntries(
    columns.map(([columnName, type, target]) => [
      columnName,
      creaColonna(columnName, type, target),
    ]),
  );
  const table = pgTable(name, columnMap as any, (tableColumns: any) => [
    ...uniques.map(([constraintName, names]) => {
      const [first, ...rest] = names.map((columnName) => tableColumns[columnName]);
      return uniqueIndex(nomeVincolo(name, constraintName, names)).on(first, ...rest);
    }),
    ...checks.map(([constraintName, expression]) => check(constraintName, sql.raw(expression))),
    ...indexes.map(([indexName, isUnique, names]) => {
      const [first, ...rest] = names.map((columnName) => tableColumns[columnName]);
      return isUnique ? uniqueIndex(indexName).on(first, ...rest) : index(indexName).on(first, ...rest);
    }),
  ]);
  exportedTables[name] = table;
  return table;
}

// L'ordine segue le dipendenze FK del modello SQLAlchemy.
export const emoji = creaTabella(definitions[0]);
export const entita = creaTabella(definitions[1]);
export const sito = creaTabella(definitions[2]);
export const sonda = creaTabella(definitions[3]);
export const utente = creaTabella(definitions[4]);
export const valutazione = creaTabella(definitions[5]);
export const elemento_grezzo = creaTabella(definitions[6]);
export const lavoro = creaTabella(definitions[7]);
export const legame_entita = creaTabella(definitions[8]);
export const legame_sito = creaTabella(definitions[9]);
export const modello = creaTabella(definitions[10]);
export const parola_chiave = creaTabella(definitions[11]);
export const punteggio = creaTabella(definitions[12]);
export const sessione_utente = creaTabella(definitions[13]);
export const snapshot = creaTabella(definitions[14]);
export const adm_caricamento = creaTabella(definitions[15]);
export const canale = creaTabella(definitions[16]);
export const etichetta = creaTabella(definitions[17]);
export const evento_sportivo = creaTabella(definitions[18]);
export const indicatore = creaTabella(definitions[19]);
export const media = creaTabella(definitions[20]);
export const puntata = creaTabella(definitions[21]);
export const registro_voce = creaTabella(definitions[22]);
export const revisione = creaTabella(definitions[23]);
export const adm_concessionario = creaTabella(definitions[24]);
export const adm_sito_inibito = creaTabella(definitions[25]);
export const avviso = creaTabella(definitions[26]);
export const estrazione = creaTabella(definitions[27]);
export const legal_entity = creaTabella(definitions[28]);
export const quota_evento = creaTabella(definitions[29]);
export const menzione_entita = creaTabella(definitions[30]);
