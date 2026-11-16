import assert from "node:assert/strict";
import { describe, it } from "node:test";
import ExcelJS from "exceljs";
import { parseExportQuery } from "./export-query";
import { canExportRestrictedBettors } from "./permissions";
import { createWorkbook, type WorkbookData, type WorkbookScope } from "./workbook";

const scopes: WorkbookScope[] = [
  "all",
  "sources",
  "evidence",
  "sites",
  "entities",
  "events",
  "bettors",
  "trust",
  "audit",
];

const workbookData: WorkbookData = {
  sources: [{
    id: 7,
    name: "Fonte autorizzata",
    provider: "Registro pubblico",
    url: "https://example.test/source",
    category: "regulatory",
    accessMethod: "manual",
    owner: "Team",
    purpose: "Verifica",
    scope: "Avvisi pubblici",
    dataCategories: ["licenza"],
    authorizationBasis: "Fonte pubblica",
    authorizationEvidenceName: null,
    validFrom: "2026-01-01",
    validUntil: null,
    reviewerRole: "compliance_reviewer",
    legalStatus: "approved",
    connectorStatus: "off",
    connectorScopes: [],
    reviewNote: null,
  } as unknown as WorkbookData["sources"][number]],
  evidence: [{
    id: 11,
    title: "=1+1",
    channel: "web",
    sourceId: 7,
    originalUrl: "https://example.test/source",
    capturedAt: new Date("2026-01-02T00:00:00.000Z"),
    rawContent: "+SUM(A1:A2)",
    categories: ["@dato"],
    extractedFacts: "-3",
    normalizedFields: { formula: "=2+2" },
    enrichmentNotes: "@header",
    status: "new",
    relatedSiteId: null,
    eventId: null,
    entityId: null,
    attachmentName: null,
    synthetic: false,
  } as unknown as WorkbookData["evidence"][number]],
  sites: [],
  entities: [],
  events: [],
  scores: [],
  activity: [],
  bettors: [{
    id: 19,
    pseudonymousId: "P-7F2A",
    operator: "Operatore demo",
    periodStart: "2026-01-01",
    periodEnd: "2026-01-31",
    averageBet: "25.00",
    grossWinnings: "125.00",
    winRate: "0.2",
    dataBasis: "Dati sintetici di prova",
    synthetic: true,
    riskNote: "Record di test",
  } as unknown as WorkbookData["bettors"][number]],
};

async function openWorkbook(scope: WorkbookScope, includeRestricted = false) {
  const bytes = await createWorkbook(scope, includeRestricted, workbookData, "2026-11-16T12:00:00.000Z");
  const workbook = new ExcelJS.Workbook();
  const workbookBytes = Buffer.alloc(bytes.length);
  bytes.copy(workbookBytes);
  await workbook.xlsx.load(
    workbookBytes as unknown as Parameters<typeof workbook.xlsx.load>[0],
  );
  return workbook;
}

describe("creazione workbook Excel", () => {
  it("genera e riapre un XLSX valido per ogni ambito", async () => {
    for (const scope of scopes) {
      const workbook = await openWorkbook(scope, scope === "bettors");
      assert.ok(workbook.worksheets.length > 0, `workbook vuoto per ${scope}`);
      assert.equal(workbook.worksheets[0]?.name, "Riepilogo");
    }
  });

  it("mantiene i nomi dei fogli, la metodologia e i riferimenti di lineage", async () => {
    const all = await openWorkbook("all");
    assert.deepEqual(all.worksheets.map((sheet) => sheet.name), [
      "Riepilogo",
      "Fonti",
      "Evidenze",
      "Siti",
      "Entità",
      "Eventi sportivi",
      "Indice affidabilità",
      "Registro attività",
      "Metodologia",
    ]);
    assert.equal(all.getWorksheet("Evidenze")?.getCell("D2").value, 7);
    assert.equal(all.getWorksheet("Metodologia")?.getCell("A2").value, "Punteggio di vulnerabilità");
    assert.match(String(all.getWorksheet("Metodologia")?.getCell("B20").value), /non costituisce parere legale/);

    const events = await openWorkbook("events");
    assert.deepEqual(events.worksheets.map((sheet) => sheet.name), [
      "Riepilogo",
      "Eventi sportivi",
      "Metodologia",
    ]);
  });

  it("esclude i profili scommettitori per impostazione predefinita", async () => {
    const workbook = await openWorkbook("all");
    assert.equal(workbook.getWorksheet("Profili scommettitori"), undefined);
    assert.equal(workbook.getWorksheet("Riepilogo")?.getCell("B4").value, "No");
  });

  it("include i profili solo quando richiesti nell’ambito compatibile", async () => {
    const all = await openWorkbook("all", true);
    const bettors = await openWorkbook("bettors", true);
    const sites = await openWorkbook("sites", true);
    assert.equal(all.getWorksheet("Profili scommettitori")?.getCell("B2").value, "P-7F2A");
    assert.equal(bettors.getWorksheet("Profili scommettitori")?.getCell("B2").value, "P-7F2A");
    assert.equal(sites.getWorksheet("Profili scommettitori"), undefined);
    assert.equal(sites.getWorksheet("Riepilogo")?.getCell("B4").value, "No");
  });

  it("tratta come testo i valori che iniziano con caratteri formula", async () => {
    const workbook = await openWorkbook("evidence");
    const evidence = workbook.getWorksheet("Evidenze");
    assert.equal(evidence?.getCell("B2").value, "'=1+1");
    assert.equal(evidence?.getCell("G2").value, "'+SUM(A1:A2)");
    assert.equal(evidence?.getCell("I2").value, "'-3");
    assert.equal(evidence?.getCell("H2").value, "[\"@dato\"]");
    assert.equal(evidence?.getCell("K2").value, "'@header");
    assert.equal(evidence?.getCell("J2").value, "{\"formula\":\"=2+2\"}");
  });
});

describe("parametri dell’esportazione", () => {
  it("interpreta la stringa false come esclusione dei dati riservati", () => {
    const parsed = parseExportQuery({ scope: "all", includeRestricted: "false" });
    assert.equal(parsed.success, true);
    if (parsed.success) assert.equal(parsed.data.includeRestricted, false);
  });

  it("accetta l’inclusione esplicita e rifiuta valori non booleani", () => {
    const allowed = parseExportQuery({ scope: "bettors", includeRestricted: "true" });
    const invalid = parseExportQuery({ scope: "bettors", includeRestricted: "yes" });
    assert.equal(allowed.success, true);
    if (allowed.success) assert.equal(allowed.data.includeRestricted, true);
    assert.equal(invalid.success, false);
  });
});

describe("autorizzazione all’esportazione dei profili riservati", () => {
  it("consente solo i ruoli previsti", () => {
    for (const role of ["admin", "compliance_reviewer", "restricted_analyst"]) {
      assert.equal(canExportRestrictedBettors(role, "active"), true, `${role} deve poter esportare`);
    }
  });

  it("nega ruoli non autorizzati, profili inattivi e ruoli assenti", () => {
    for (const role of ["analyst", "read_only", "pending", "unknown", null, undefined]) {
      assert.equal(canExportRestrictedBettors(role, "active"), false, `${String(role)} non deve poter esportare`);
    }
    assert.equal(canExportRestrictedBettors("admin", "pending"), false);
  });
});
