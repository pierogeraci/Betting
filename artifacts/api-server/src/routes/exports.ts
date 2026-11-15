import ExcelJS from "exceljs";
import { desc } from "drizzle-orm";
import { Router, type IRouter } from "express";
import { DownloadWorkbookQueryParams } from "@workspace/api-zod";
import {
  db,
  ctiActivityTable,
  ctiBettorsTable,
  ctiEntitiesTable,
  ctiEventsTable,
  ctiEvidenceTable,
  ctiSitesTable,
  ctiSourcesTable,
  ctiTrustScoresTable,
} from "@workspace/db";
import { requireRole } from "../lib/auth";
import {
  trustCalibrationNotice,
  trustFactorDefinitions,
} from "../lib/cti-utils";

const router: IRouter = Router();
const exportRoles = ["admin", "analyst", "compliance_reviewer"] as const;
const restrictedExportRoles = ["admin", "compliance_reviewer"] as const;
const contentType =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

function cell(value: unknown) {
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
  for (const row of rows) sheet.addRow(row.map(cell));
  sheet.views = [{ state: "frozen", ySplit: 1 }];
  sheet.autoFilter = {
    from: { row: 1, column: 1 },
    to: { row: 1, column: Math.max(headers.length, 1) },
  };
  sheet.getRow(1).font = { bold: true };
  sheet.columns.forEach((column, index) => {
    const values = sheet.getColumn(index + 1).values.slice(1, 18);
    column.width = Math.min(
      Math.max(
        14,
        ...values.map((value) => String(value ?? "").length + 2),
      ),
      48,
    );
  });
}

router.get(
  "/exports/xlsx",
  requireRole(...exportRoles),
  async (req, res): Promise<void> => {
    const parsed = DownloadWorkbookQueryParams.safeParse(req.query);
    if (!parsed.success) {
      res.status(400).json({ error: parsed.error.message });
      return;
    }
    const { scope = "all", includeRestricted = false } = parsed.data;
    if (includeRestricted && !restrictedExportRoles.includes(req.ctiUser!.role as (typeof restrictedExportRoles)[number])) {
      res.status(403).json({ error: "Only compliance reviewers and administrators can export restricted profiles" });
      return;
    }
    if (scope === "bettors" && !includeRestricted) {
      res.status(403).json({ error: "Explicit approval is required to export restricted bettor profiles" });
      return;
    }

    const workbook = new ExcelJS.Workbook();
    workbook.creator = "CTI Gambling Intelligence";
    workbook.created = new Date();
    workbook.subject = "Authorized-source intelligence extraction";
    workbook.title = "CTI Intelligence Workbook";
    const generatedAt = new Date().toISOString();
    const [sources, evidence, sites, entities, events, scores, activity, bettors] =
      await Promise.all([
        db.select().from(ctiSourcesTable).orderBy(desc(ctiSourcesTable.updatedAt)),
        db.select().from(ctiEvidenceTable).orderBy(desc(ctiEvidenceTable.capturedAt)),
        db.select().from(ctiSitesTable).orderBy(desc(ctiSitesTable.updatedAt)),
        db.select().from(ctiEntitiesTable).orderBy(desc(ctiEntitiesTable.createdAt)),
        db.select().from(ctiEventsTable).orderBy(desc(ctiEventsTable.startsAt)),
        db.select().from(ctiTrustScoresTable).orderBy(desc(ctiTrustScoresTable.computedAt)),
        db.select().from(ctiActivityTable).orderBy(desc(ctiActivityTable.createdAt)),
        includeRestricted || scope === "bettors"
          ? db.select().from(ctiBettorsTable).orderBy(desc(ctiBettorsTable.createdAt))
          : Promise.resolve([]),
      ]);

    addSheet(workbook, "Overview", ["Field", "Value"], [
      ["Generated at", generatedAt],
      ["Requested scope", scope],
      ["Restricted profiles included", includeRestricted ? "Yes" : "No"],
      ["Sources", sources.length],
      ["Evidence records", evidence.length],
      ["Betting sites", sites.length],
      ["Legal entities", entities.length],
      ["Sports events", events.length],
      ["Trust score calculations", scores.length],
      ["Bettor profiles", includeRestricted ? bettors.length : "Not included (restricted)"],
      ["Data policy", "Manual inputs and authorized sources only; credentials are never exported."],
      ["Scoring status", "Provisional; validate/calibrate before operational use."],
    ]);

    const requestedSheets = (key: string) => scope === "all" || scope === key;
    if (requestedSheets("sources")) {
      addSheet(workbook, "Sources", [
        "ID", "Name", "Provider", "URL", "Category", "Access method", "Owner",
        "Purpose", "Scope", "Data categories", "Authorization basis",
        "Authorization evidence", "Valid from", "Valid until", "Reviewer role",
        "Legal status", "Connector status", "Connector scopes", "Review note",
      ], sources.map((row) => [
        row.id, row.name, row.provider, row.url, row.category, row.accessMethod,
        row.owner, row.purpose, row.scope, row.dataCategories,
        row.authorizationBasis, row.authorizationEvidenceName, row.validFrom,
        row.validUntil, row.reviewerRole, row.legalStatus, row.connectorStatus,
        row.connectorScopes, row.reviewNote,
      ]));
    }
    if (requestedSheets("evidence")) {
      addSheet(workbook, "Evidence", [
        "ID", "Title", "Channel", "Source ID", "Original URL", "Captured at",
        "Raw content", "Categories", "Extracted facts", "Normalized fields",
        "Enrichment notes", "Status", "Site ID", "Event ID", "Entity ID",
        "Attachment", "Synthetic",
      ], evidence.map((row) => [
        row.id, row.title, row.channel, row.sourceId, row.originalUrl,
        row.capturedAt, row.rawContent, row.categories, row.extractedFacts,
        row.normalizedFields, row.enrichmentNotes, row.status, row.relatedSiteId,
        row.eventId, row.entityId, row.attachmentName, row.synthetic,
      ]));
    }
    if (requestedSheets("sites")) {
      addSheet(workbook, "Sites", [
        "ID", "Domain", "Name", "Description", "First seen", "Last seen",
        "Jurisdiction", "License claim", "Legal entity ID", "Entity link status",
        "Risk band", "Trust Index",
      ], sites.map((row) => [
        row.id, row.domain, row.name, row.description, row.firstSeenAt,
        row.lastSeenAt, row.jurisdiction, row.licenseClaim, row.legalEntityId,
        row.entityLinkStatus, row.riskBand, row.trustIndex,
      ]));
    }
    if (requestedSheets("entities")) {
      addSheet(workbook, "Entities", [
        "ID", "Name", "Type", "Country", "Registration ID", "Evidence notes",
      ], entities.map((row) => [
        row.id, row.name, row.entityType, row.country, row.registrationId,
        row.evidenceNotes,
      ]));
    }
    if (requestedSheets("events")) {
      addSheet(workbook, "Sports Events", [
        "ID", "Sport", "Competition", "Home", "Away", "Start time",
        "Odds sources", "Market volume", "Unusual odds", "Event risk band",
        "Rating note", "Rating details", "Synthetic",
      ], events.map((row) => [
        row.id, row.sport, row.competition, row.home, row.away, row.startsAt,
        row.oddsSources, row.marketVolume, row.unusualOdds, row.riskBand,
        row.ratingNote, row.ratingDetails, row.synthetic,
      ]));
    }
    if (requestedSheets("trust")) {
      addSheet(workbook, "Trust Index", [
        "ID", "Site ID", "Vulnerability score", "Vulnerability band",
        "Threat score", "Threat band", "Normalized vulnerability",
        "Normalized threat", "Trust Index", "Trust band", "Factor detail",
        "Threat detail", "Analyst note", "Calibration notice", "Computed at",
      ], scores.map((row) => [
        row.id, row.siteId, row.vulnerabilityScore, row.vulnerabilityBand,
        row.threatScore, row.threatBand, row.normalizedVulnerability,
        row.normalizedThreat, row.trustIndex, row.trustBand,
        row.factorDetails, row.threatDetails, row.analystNote,
        row.calibrationNotice, row.computedAt,
      ]));
    }
    if (requestedSheets("bettors") && includeRestricted) {
      addSheet(workbook, "Bettor Profiles", [
        "ID", "Pseudonymous ID", "Operator", "Period start", "Period end",
        "Average bet", "Gross winnings", "Win rate", "Data basis",
        "Synthetic", "Risk note",
      ], bettors.map((row) => [
        row.id, row.pseudonymousId, row.operator, row.periodStart, row.periodEnd,
        row.averageBet, row.grossWinnings, row.winRate, row.dataBasis,
        row.synthetic, row.riskNote,
      ]));
    }
    if (requestedSheets("audit")) {
      addSheet(workbook, "Audit Log", [
        "ID", "Action", "Entity type", "Entity ID", "Entity label",
        "Actor reference", "Created at",
      ], activity.map((row) => [
        row.id, row.action, row.entityType, row.entityId, row.entityLabel,
        row.actorId, row.createdAt,
      ]));
    }
    if (scope === "all" || scope === "trust" || scope === "events") {
      addSheet(workbook, "Methodology", ["Item", "Definition"], [
        ["Vulnerability score", "Sum of binary vulnerability indicators multiplied by their approved prototype weights; range 0–20."],
        ...trustFactorDefinitions.map((factor) => [factor.label, `Weight ${factor.weight}`]),
        ["Vulnerability bands", "Low < 6; medium >= 6 and < 12; high >= 12."],
        ["Threat score", "Sum of three 1–3 levels; range 3–9."],
        ["Average bet", "Low < €50; medium >= €50 and < €250; high >= €250."],
        ["Gross winnings", "Low < €1,000; medium >= €1,000 and < €5,000; high >= €5,000."],
        ["Win rate", "Low < 25%; medium >= 25% and < 50%; high >= 50%."],
        ["Trust Index", "Average of vulnerabilityScore/20*100 and (threatScore-3)/6*100."],
        ["Trust Index bands", "Low < 33; medium >= 33 and < 67; high >= 67."],
        ["Event rating", "Separate provisional heuristic: limited odds-source count (<3) adds 1; unusual odds adds 2; volume >= €10,000 adds 1 and >= €50,000 adds 2. Low 0–1; medium 2–3; high >= 4."],
        ["Event rating limitation", "A prototype rule only; it is not an established fraud probability and requires calibration against authorized historical data."],
        ["Calibration", trustCalibrationNotice],
        ["Source permission", "A source record or review is not legal advice or a grant of access rights."],
        ["Privacy", "No credential values or direct bettor identity fields are included."],
      ]);
    }

    const buffer = await workbook.xlsx.writeBuffer();
    const filename = `cti-extraction-${new Date().toISOString().slice(0, 10)}.xlsx`;
    res.setHeader("Content-Type", contentType);
    res.setHeader("Content-Disposition", `attachment; filename="${filename}"`);
    res.setHeader("Cache-Control", "no-store");
    res.send(Buffer.from(buffer));
  },
);

export default router;
