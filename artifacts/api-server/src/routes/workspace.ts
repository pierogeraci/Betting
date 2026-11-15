import { desc } from "drizzle-orm";
import { Router, type IRouter } from "express";
import {
  GetDashboardSummaryResponse,
  ListActivityQueryParams,
  ListActivityResponse,
} from "@workspace/api-zod";
import {
  db,
  ctiActivityTable,
  ctiBettorsTable,
  ctiEvidenceTable,
  ctiEventsTable,
  ctiSitesTable,
  ctiSourcesTable,
} from "@workspace/db";
import { recordActivity } from "../lib/cti-utils";

const router: IRouter = Router();

router.get("/dashboard/summary", async (_req, res): Promise<void> => {
  const [sources, evidence, sites, events, bettors] = await Promise.all([
    db.select().from(ctiSourcesTable),
    db.select().from(ctiEvidenceTable),
    db.select().from(ctiSitesTable),
    db.select().from(ctiEventsTable),
    db.select({ id: ctiBettorsTable.id }).from(ctiBettorsTable),
  ]);
  const today = new Date().toISOString().slice(0, 10);
  const approvedSources = sources.filter(
    (source) =>
      source.legalStatus === "approved" &&
      source.validFrom <= today &&
      (!source.validUntil || source.validUntil >= today),
  ).length;
  const response = GetDashboardSummaryResponse.parse({
    sourceCount: sources.length,
    sourcesInReview: sources.filter((source) => source.legalStatus === "in_review").length,
    approvedSources,
    evidenceCount: evidence.length,
    unclassifiedEvidence: evidence.filter((item) => item.status === "new").length,
    siteCount: sites.length,
    highRiskSites: sites.filter((site) => site.riskBand === "high").length,
    eventCount: events.length,
    highRiskEvents: events.filter((event) => event.riskBand === "high").length,
    restrictedBettorCount: bettors.length,
    generatedAt: new Date().toISOString(),
  });
  res.json(response);
});

router.get("/activity", async (req, res): Promise<void> => {
  const parsed = ListActivityQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  const limit = parsed.data.limit ?? 25;
  const items = await db
    .select()
    .from(ctiActivityTable)
    .orderBy(desc(ctiActivityTable.createdAt))
    .limit(limit);
  res.json(
    ListActivityResponse.parse({
      items: items.map((item) => ({
        ...item,
        actorId: "anonymous",
        actorLabel: "Operatore anonimo",
        createdAt: item.createdAt.toISOString(),
      })),
      total: items.length,
    }),
  );
});

export default router;
