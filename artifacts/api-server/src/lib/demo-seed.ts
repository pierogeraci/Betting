import { sql } from "drizzle-orm";
import {
  db,
  ctiActivityTable,
  ctiBettorsTable,
  ctiEntitiesTable,
  ctiEvidenceTable,
  ctiEventsTable,
  ctiSitesTable,
  ctiSourcesTable,
  ctiTrustScoresTable,
} from "@workspace/db";
import { calculateEventRisk, calculateTrust } from "./cti-utils";

const seedActor = "demo-seed";
const demoLabel = "Synthetic demonstration record — not real-world intelligence.";

async function workspaceHasOperationalData() {
  const tables = [
    ctiSourcesTable,
    ctiEvidenceTable,
    ctiSitesTable,
    ctiEntitiesTable,
    ctiEventsTable,
    ctiBettorsTable,
    ctiTrustScoresTable,
  ];
  const counts = await Promise.all(
    tables.map(async (table) => {
      const [row] = await db
        .select({ count: sql<number>`count(*)::int` })
        .from(table);
      return Number(row?.count ?? 0);
    }),
  );
  return counts.some((count) => count > 0);
}

export async function seedDevelopmentDemoData() {
  if (process.env.NODE_ENV === "production") return false;
  if (await workspaceHasOperationalData()) return false;

  return db.transaction(async (tx) => {
    const [existing] = await tx
      .select({ count: sql<number>`count(*)::int` })
      .from(ctiSourcesTable);
    if (Number(existing?.count ?? 0) > 0) return false;

    const now = new Date();
    const today = now.toISOString().slice(0, 10);
    const validUntil = new Date(now.getTime() + 365 * 24 * 60 * 60 * 1000)
      .toISOString()
      .slice(0, 10);
    const [approvedSource] = await tx
      .insert(ctiSourcesTable)
      .values({
        name: "Synthetic public market bulletin",
        provider: "CTI example publisher",
        url: "https://market.example/",
        category: "market_data",
        accessMethod: "manual",
        owner: "Demonstration workspace",
        purpose: "Show the authorized-source review and evidence workflow",
        scope: "Synthetic sample only; no live collection or external feed",
        dataCategories: ["market notices", "sample odds observations"],
        authorizationBasis: "Demonstration-only synthetic record; not a legal authorization",
        authorizationEvidenceName: null,
        authorizationEvidencePath: null,
        validFrom: today,
        validUntil,
        reviewerRole: "compliance_reviewer",
        reviewerId: "demo-reviewer",
        legalStatus: "approved",
        connectorStatus: "not_configured",
        connectorScopes: [],
        secretReference: "",
        reviewNote: "Synthetic example for interface demonstration.",
        createdBy: seedActor,
      })
      .returning({ id: ctiSourcesTable.id });
    const [reviewSource] = await tx
      .insert(ctiSourcesTable)
      .values({
        name: "Synthetic operator disclosure",
        provider: "Example operator",
        url: "https://operator.example/disclosure",
        category: "operator",
        accessMethod: "manual",
        owner: "Demonstration workspace",
        purpose: "Show review-pending source handling",
        scope: "Synthetic sample text only",
        dataCategories: ["licensing", "ownership"],
        authorizationBasis: "Synthetic example; review required before any real use",
        validFrom: today,
        reviewerRole: "compliance_reviewer",
        legalStatus: "in_review",
        connectorStatus: "not_configured",
        connectorScopes: [],
        secretReference: "",
        createdBy: seedActor,
      })
      .returning({ id: ctiSourcesTable.id });

    const [entity] = await tx
      .insert(ctiEntitiesTable)
      .values({
        name: "Example Holdings S.r.l. (synthetic)",
        entityType: "company",
        country: "IT",
        registrationId: "SYNTHETIC-NOT-REAL",
        evidenceNotes: `${demoLabel} Candidate association requires analyst confirmation.`,
        createdBy: seedActor,
      })
      .returning({ id: ctiEntitiesTable.id });
    const [site] = await tx
      .insert(ctiSitesTable)
      .values({
        domain: "sportsbook-alpha.example",
        name: "Alpha Sportsbook (synthetic)",
        description: `${demoLabel} Example record for site profiling.`,
        firstSeenAt: now,
        lastSeenAt: now,
        jurisdiction: "Unverified — synthetic",
        licenseClaim: "Example claim only; not checked",
        legalEntityId: entity.id,
        entityLinkStatus: "candidate",
        riskBand: "unassessed",
        createdBy: seedActor,
      })
      .returning({ id: ctiSitesTable.id });
    const [secondSite] = await tx
      .insert(ctiSitesTable)
      .values({
        domain: "sportsbook-beta.example",
        name: "Beta Sportsbook (synthetic)",
        description: `${demoLabel} Example record without an entity attribution.`,
        firstSeenAt: new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000),
        lastSeenAt: now,
        jurisdiction: "Unverified — synthetic",
        licenseClaim: "No claim recorded in this sample",
        entityLinkStatus: "unlinked",
        riskBand: "unassessed",
        createdBy: seedActor,
      })
      .returning({ id: ctiSitesTable.id });

    const sampleEventRisk = calculateEventRisk({
      oddsSources: 2,
      marketVolume: 12000,
      unusualOdds: true,
    });
    const [event] = await tx
      .insert(ctiEventsTable)
      .values({
        sport: "Football",
        competition: "Synthetic Demo Cup",
        home: "Example City",
        away: "Sample United",
        startsAt: new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000),
        oddsSources: 2,
        marketVolume: "12000",
        unusualOdds: true,
        riskBand: sampleEventRisk.riskBand,
        ratingNote: `${demoLabel} ${sampleEventRisk.note}`,
        ratingDetails: {
          ...sampleEventRisk.details,
          provisionalScore: sampleEventRisk.score,
          dataBasis: "Synthetic data only",
        },
        synthetic: true,
        createdBy: seedActor,
      })
      .returning({ id: ctiEventsTable.id });

    await tx.insert(ctiEvidenceTable).values([
      {
        title: "Synthetic market notice",
        channel: "web",
        sourceId: approvedSource.id,
        originalUrl: "https://market.example/sample-notice",
        capturedAt: now,
        rawContent: `${demoLabel} Example notice: an operator publishes a fictional market update.`,
        categories: ["market notice", "operator"],
        extractedFacts: { operatorName: "Alpha Sportsbook (synthetic)", observation: "Example update" },
        normalizedFields: { operatorDomain: "sportsbook-alpha.example", noticeType: "sample" },
        enrichmentNotes: "Demonstration only; facts and names are invented.",
        status: "normalized",
        relatedSiteId: site.id,
        eventId: event.id,
        entityId: entity.id,
        synthetic: true,
        createdBy: seedActor,
      },
      {
        title: "Synthetic ownership observation",
        channel: "document",
        sourceId: reviewSource.id,
        originalUrl: null,
        capturedAt: new Date(now.getTime() - 2 * 24 * 60 * 60 * 1000),
        rawContent: `${demoLabel} Example statement references an unnamed corporate relationship.`,
        categories: ["ownership", "entity candidate"],
        extractedFacts: { observation: "Fictional relationship mentioned", confidence: "low" },
        normalizedFields: { relationshipType: "candidate", verified: false },
        enrichmentNotes: "Not sufficient to attribute a person or legal entity.",
        status: "classified",
        relatedSiteId: secondSite.id,
        eventId: null,
        entityId: null,
        synthetic: true,
        createdBy: seedActor,
      },
    ]);

    await tx.insert(ctiBettorsTable).values({
      pseudonymousId: "SYN-P-001",
      operator: "Alpha Sportsbook (synthetic)",
      periodStart: new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
        .toISOString()
        .slice(0, 10),
      periodEnd: today,
      averageBet: "100",
      grossWinnings: "2600",
      winRate: "0.36000",
      dataBasis: "Synthetic demonstration figures; no real person or account",
      synthetic: true,
      riskNote: "Sample only; not an inference about a real bettor.",
      createdBy: seedActor,
    });

    const trust = calculateTrust(
      [
        { key: "multiple_accounts", present: false },
        { key: "eu_bank_payment", present: true },
        { key: "no_registration", present: true },
        { key: "no_identity_documents", present: false },
        { key: "third_party_provider", present: false },
        { key: "crypto_payment_or_betting", present: true },
        { key: "offshore_bank_account", present: false },
      ],
      { averageBet: 100, grossWinnings: 2600, winRate: 0.36 },
    );
    await tx.insert(ctiTrustScoresTable).values({
      siteId: site.id,
      vulnerabilityScore: String(trust.vulnerabilityScore),
      vulnerabilityBand: trust.vulnerabilityBand,
      threatScore: trust.threatScore,
      threatBand: trust.threatBand,
      normalizedVulnerability: String(trust.normalizedVulnerability),
      normalizedThreat: String(trust.normalizedThreat),
      trustIndex: String(trust.trustIndex),
      trustBand: trust.trustBand,
      factorDetails: trust.factorDetails,
      threatDetails: trust.threatDetails,
      analystNote: `${demoLabel} Use only to inspect the calculation workflow.`,
      calibrationNotice: trust.calibrationNotice,
      createdBy: seedActor,
    });
    await tx
      .update(ctiSitesTable)
      .set({
        trustIndex: String(trust.trustIndex),
        riskBand: trust.trustBand,
        updatedAt: now,
      })
      .where(sql`${ctiSitesTable.id} = ${site.id}`);

    await tx.insert(ctiActivityTable).values([
      {
        action: "demo_data_seeded",
        entityType: "workspace",
        entityId: "demo",
        entityLabel: "Synthetic demonstration dataset",
        actorId: seedActor,
        actorLabel: "System demo setup",
      },
      {
        action: "trust_score_calculated",
        entityType: "site",
        entityId: String(site.id),
        entityLabel: "Alpha Sportsbook (synthetic)",
        actorId: seedActor,
        actorLabel: "System demo setup",
      },
    ]);

    return true;
  });
}
