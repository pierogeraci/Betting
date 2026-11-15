import { and, desc, eq, ilike, or, sql } from "drizzle-orm";
import { Router, type IRouter } from "express";
import {
  CalculateTrustScoreBody,
  CalculateTrustScoreResponse,
  ClassifyEvidenceBody,
  ClassifyEvidenceParams,
  ClassifyEvidenceResponse,
  CreateBettorBody,
  CreateBettorResponse,
  CreateEntityBody,
  CreateEntityResponse,
  CreateEventBody,
  CreateEventResponse,
  CreateEvidenceBody,
  CreateEvidenceResponse,
  CreateSiteBody,
  CreateSiteResponse,
  GetEventParams,
  GetEventResponse,
  GetEvidenceParams,
  GetEvidenceResponse,
  GetSiteParams,
  GetSiteProfileParams,
  GetSiteProfileResponse,
  GetSiteResponse,
  ListBettorsQueryParams,
  ListBettorsResponse,
  ListEntitiesQueryParams,
  ListEntitiesResponse,
  ListEventsQueryParams,
  ListEventsResponse,
  ListEvidenceQueryParams,
  ListEvidenceResponse,
  ListSitesQueryParams,
  ListSitesResponse,
  ListTrustScoresQueryParams,
  ListTrustScoresResponse,
  LinkSiteEntityBody,
  LinkSiteEntityParams,
  LinkSiteEntityResponse,
  RateEventBody,
  RateEventParams,
  RateEventResponse,
  GetTrustMatrixResponse,
  UpdateEventBody,
  UpdateEventParams,
  UpdateEventResponse,
  UpdateEvidenceBody,
  UpdateEvidenceParams,
  UpdateEvidenceResponse,
  UpdateSiteBody,
  UpdateSiteParams,
  UpdateSiteResponse,
} from "@workspace/api-zod";
import {
  db,
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
  calculateEventRisk,
  calculateTrust,
  isSafeObjectPath,
  recordActivity,
  toIso,
  toNumber,
  trustCalibrationNotice,
  trustFactorDefinitions,
  toSqlDate,
} from "../lib/cti-utils";

const router: IRouter = Router();
const analystRoles = ["admin", "analyst", "compliance_reviewer"] as const;
const restrictedRoles = ["admin", "compliance_reviewer", "restricted_analyst"] as const;

function mapEvidence(row: typeof ctiEvidenceTable.$inferSelect) {
  return { ...row, capturedAt: row.capturedAt.toISOString(), createdAt: row.createdAt.toISOString() };
}

async function mapSite(row: typeof ctiSitesTable.$inferSelect) {
  const [countRow] = await db
    .select({ count: sql<number>`count(*)::int` })
    .from(ctiEvidenceTable)
    .where(eq(ctiEvidenceTable.relatedSiteId, row.id));
  return {
    ...row,
    firstSeenAt: toIso(row.firstSeenAt),
    lastSeenAt: toIso(row.lastSeenAt),
    trustIndex: toNumber(row.trustIndex),
    evidenceCount: Number(countRow?.count ?? 0),
    createdAt: row.createdAt.toISOString(),
  };
}

function mapEvent(row: typeof ctiEventsTable.$inferSelect) {
  return {
    ...row,
    startsAt: row.startsAt.toISOString(),
    marketVolume: toNumber(row.marketVolume),
    createdAt: row.createdAt.toISOString(),
  };
}

function mapBettor(row: typeof ctiBettorsTable.$inferSelect) {
  return {
    ...row,
    averageBet: Number(row.averageBet),
    grossWinnings: Number(row.grossWinnings),
    winRate: Number(row.winRate),
    createdAt: row.createdAt.toISOString(),
  };
}

function mapTrustScore(row: typeof ctiTrustScoresTable.$inferSelect) {
  return {
    ...row,
    vulnerabilityScore: Number(row.vulnerabilityScore),
    normalizedVulnerability: Number(row.normalizedVulnerability),
    normalizedThreat: Number(row.normalizedThreat),
    trustIndex: Number(row.trustIndex),
    computedAt: row.computedAt.toISOString(),
  };
}

async function validateEvidenceSource(
  sourceId: number | null | undefined,
  synthetic: boolean | undefined,
) {
  if (synthetic) return null;
  if (!sourceId) return "Select an approved source or mark the record as synthetic";
  const today = new Date().toISOString().slice(0, 10);
  const [source] = await db
    .select()
    .from(ctiSourcesTable)
    .where(eq(ctiSourcesTable.id, sourceId))
    .limit(1);
  if (!source) return "Source not found";
  if (
    source.legalStatus !== "approved" ||
    source.validFrom > today ||
    (source.validUntil !== null && source.validUntil < today)
  ) {
    return "Evidence cannot be linked to a source without current approved authorization";
  }
  return null;
}

function normalizeDomain(value: string) {
  const input = value.trim();
  try {
    const url = new URL(input.includes("://") ? input : `https://${input}`);
    const host = url.hostname.toLowerCase().replace(/^www\./, "");
    if (!host.includes(".") || host.includes("..")) return null;
    return host;
  } catch {
    return null;
  }
}

router.get("/evidence", async (req, res): Promise<void> => {
  const parsed = ListEvidenceQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  const filters = [];
  if (parsed.data.q) {
    const pattern = `%${parsed.data.q}%`;
    filters.push(or(ilike(ctiEvidenceTable.title, pattern), ilike(ctiEvidenceTable.rawContent, pattern))!);
  }
  if (parsed.data.status) filters.push(eq(ctiEvidenceTable.status, parsed.data.status));
  const rows = await db
    .select()
    .from(ctiEvidenceTable)
    .where(filters.length ? and(...filters) : undefined)
    .orderBy(desc(ctiEvidenceTable.capturedAt));
  const items = rows.map(mapEvidence);
  res.json(ListEvidenceResponse.parse({ items, total: items.length }));
});

router.post(
  "/evidence",
  requireRole(...analystRoles),
  async (req, res): Promise<void> => {
    const parsed = CreateEvidenceBody.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: parsed.error.message });
      return;
    }
    const input = parsed.data;
    const sourceError = await validateEvidenceSource(input.sourceId, input.synthetic);
    if (sourceError) {
      res.status(400).json({ error: sourceError });
      return;
    }
    if (input.attachmentPath && !isSafeObjectPath(input.attachmentPath)) {
      res.status(400).json({ error: "Evidence attachment path is invalid" });
      return;
    }
    const [created] = await db
      .insert(ctiEvidenceTable)
      .values({
        ...input,
        capturedAt: new Date(input.capturedAt),
        createdBy: "anonymous",
      })
      .returning();
    await recordActivity(req, "Captured evidence", "evidence", created.id, created.title);
    res.status(201).json(CreateEvidenceResponse.parse(mapEvidence(created)));
  },
);

router.get("/evidence/:id", async (req, res): Promise<void> => {
  const params = GetEvidenceParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  const [row] = await db.select().from(ctiEvidenceTable).where(eq(ctiEvidenceTable.id, params.data.id)).limit(1);
  if (!row) {
    res.status(404).json({ error: "Evidence not found" });
    return;
  }
  res.json(GetEvidenceResponse.parse(mapEvidence(row)));
});

router.patch(
  "/evidence/:id",
  requireRole(...analystRoles),
  async (req, res): Promise<void> => {
    const params = UpdateEvidenceParams.safeParse(req.params);
    const body = UpdateEvidenceBody.safeParse(req.body);
    if (!params.success || !body.success) {
      res.status(400).json({ error: params.error?.message ?? body.error?.message });
      return;
    }
    const [existing] = await db.select().from(ctiEvidenceTable).where(eq(ctiEvidenceTable.id, params.data.id)).limit(1);
    if (!existing) {
      res.status(404).json({ error: "Evidence not found" });
      return;
    }
    const sourceId = body.data.sourceId === undefined ? existing.sourceId : body.data.sourceId;
    const synthetic = body.data.synthetic === undefined ? existing.synthetic : body.data.synthetic;
    const sourceError = await validateEvidenceSource(sourceId, synthetic);
    if (sourceError) {
      res.status(400).json({ error: sourceError });
      return;
    }
    if (body.data.attachmentPath && !isSafeObjectPath(body.data.attachmentPath)) {
      res.status(400).json({ error: "Evidence attachment path is invalid" });
      return;
    }
    const updateData = {
      ...body.data,
      ...(body.data.capturedAt ? { capturedAt: new Date(body.data.capturedAt) } : {}),
    };
    const [updated] = await db
      .update(ctiEvidenceTable)
      .set(updateData)
      .where(eq(ctiEvidenceTable.id, params.data.id))
      .returning();
    await recordActivity(req, "Updated evidence record", "evidence", updated.id, updated.title);
    res.json(UpdateEvidenceResponse.parse(mapEvidence(updated)));
  },
);

router.post(
  "/evidence/:id/classify",
  requireRole(...analystRoles),
  async (req, res): Promise<void> => {
    const params = ClassifyEvidenceParams.safeParse(req.params);
    const body = ClassifyEvidenceBody.safeParse(req.body);
    if (!params.success || !body.success) {
      res.status(400).json({ error: params.error?.message ?? body.error?.message });
      return;
    }
    const [updated] = await db
      .update(ctiEvidenceTable)
      .set(body.data)
      .where(eq(ctiEvidenceTable.id, params.data.id))
      .returning();
    if (!updated) {
      res.status(404).json({ error: "Evidence not found" });
      return;
    }
    await recordActivity(req, "Classified and normalized evidence", "evidence", updated.id, updated.title);
    res.json(ClassifyEvidenceResponse.parse(mapEvidence(updated)));
  },
);

router.get("/sites", async (req, res): Promise<void> => {
  const parsed = ListSitesQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  const filters = [];
  if (parsed.data.q) {
    const pattern = `%${parsed.data.q}%`;
    filters.push(or(ilike(ctiSitesTable.domain, pattern), ilike(ctiSitesTable.name, pattern))!);
  }
  if (parsed.data.riskBand) filters.push(eq(ctiSitesTable.riskBand, parsed.data.riskBand));
  const rows = await db
    .select()
    .from(ctiSitesTable)
    .where(filters.length ? and(...filters) : undefined)
    .orderBy(desc(ctiSitesTable.updatedAt));
  const items = await Promise.all(rows.map(mapSite));
  res.json(ListSitesResponse.parse({ items, total: items.length }));
});

router.post(
  "/sites",
  requireRole(...analystRoles),
  async (req, res): Promise<void> => {
    const parsed = CreateSiteBody.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: parsed.error.message });
      return;
    }
    const domain = normalizeDomain(parsed.data.domain);
    if (!domain) {
      res.status(400).json({ error: "Enter a valid domain name or URL" });
      return;
    }
    const [created] = await db
      .insert(ctiSitesTable)
      .values({
        ...parsed.data,
        domain,
        firstSeenAt: parsed.data.firstSeenAt ? new Date(parsed.data.firstSeenAt) : null,
        lastSeenAt: parsed.data.lastSeenAt ? new Date(parsed.data.lastSeenAt) : null,
        createdBy: "anonymous",
      })
      .onConflictDoNothing({ target: ctiSitesTable.domain })
      .returning();
    if (!created) {
      res.status(409).json({ error: "A site profile for this domain already exists" });
      return;
    }
    await recordActivity(req, "Created betting-site profile", "site", created.id, created.domain);
    res.status(201).json(CreateSiteResponse.parse(await mapSite(created)));
  },
);

router.get("/sites/:id", async (req, res): Promise<void> => {
  const params = GetSiteParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  const [site] = await db.select().from(ctiSitesTable).where(eq(ctiSitesTable.id, params.data.id)).limit(1);
  if (!site) {
    res.status(404).json({ error: "Site not found" });
    return;
  }
  res.json(GetSiteResponse.parse(await mapSite(site)));
});

router.patch(
  "/sites/:id",
  requireRole(...analystRoles),
  async (req, res): Promise<void> => {
    const params = UpdateSiteParams.safeParse(req.params);
    const body = UpdateSiteBody.safeParse(req.body);
    if (!params.success || !body.success) {
      res.status(400).json({ error: params.error?.message ?? body.error?.message });
      return;
    }
    const input = { ...body.data };
    if (input.domain) {
      const domain = normalizeDomain(input.domain);
      if (!domain) {
        res.status(400).json({ error: "Enter a valid domain name or URL" });
        return;
      }
      input.domain = domain;
    }
    const updateData = {
      ...input,
      ...(input.firstSeenAt !== undefined
        ? { firstSeenAt: input.firstSeenAt ? new Date(input.firstSeenAt) : null }
        : {}),
      ...(input.lastSeenAt !== undefined
        ? { lastSeenAt: input.lastSeenAt ? new Date(input.lastSeenAt) : null }
        : {}),
    };
    const [updated] = await db
      .update(ctiSitesTable)
      .set({ ...updateData, updatedAt: new Date() })
      .where(eq(ctiSitesTable.id, params.data.id))
      .returning();
    if (!updated) {
      res.status(404).json({ error: "Site not found" });
      return;
    }
    await recordActivity(req, "Updated betting-site profile", "site", updated.id, updated.domain);
    res.json(UpdateSiteResponse.parse(await mapSite(updated)));
  },
);

router.get("/sites/:id/profile", async (req, res): Promise<void> => {
  const params = GetSiteProfileParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  const [site] = await db.select().from(ctiSitesTable).where(eq(ctiSitesTable.id, params.data.id)).limit(1);
  if (!site) {
    res.status(404).json({ error: "Site not found" });
    return;
  }
  const [entity] = site.legalEntityId
    ? await db.select().from(ctiEntitiesTable).where(eq(ctiEntitiesTable.id, site.legalEntityId)).limit(1)
    : [];
  const evidenceRows = await db
    .select()
    .from(ctiEvidenceTable)
    .where(eq(ctiEvidenceTable.relatedSiteId, site.id))
    .orderBy(desc(ctiEvidenceTable.capturedAt));
  const [latestScore] = await db
    .select()
    .from(ctiTrustScoresTable)
    .where(eq(ctiTrustScoresTable.siteId, site.id))
    .orderBy(desc(ctiTrustScoresTable.computedAt))
    .limit(1);
  const payload = {
    site: await mapSite(site),
    evidence: evidenceRows.map(mapEvidence),
    latestTrustScore: latestScore ? mapTrustScore(latestScore) : null,
    linkedEntity: entity
      ? { ...entity, createdAt: entity.createdAt.toISOString() }
      : null,
  };
  res.json(GetSiteProfileResponse.parse(payload));
});

router.post(
  "/sites/:id/entity-link",
  requireRole(...analystRoles),
  async (req, res): Promise<void> => {
    const params = LinkSiteEntityParams.safeParse(req.params);
    const body = LinkSiteEntityBody.safeParse(req.body);
    if (!params.success || !body.success) {
      res.status(400).json({ error: params.error?.message ?? body.error?.message });
      return;
    }
    const [site] = await db.select().from(ctiSitesTable).where(eq(ctiSitesTable.id, params.data.id)).limit(1);
    const [entity] = await db.select().from(ctiEntitiesTable).where(eq(ctiEntitiesTable.id, body.data.legalEntityId)).limit(1);
    if (!site || !entity) {
      res.status(404).json({ error: "Site or legal-entity candidate not found" });
      return;
    }
    const linkStatus =
      body.data.decision === "confirm"
        ? "analyst_confirmed"
        : body.data.decision === "candidate"
          ? "candidate"
          : "rejected";
    const [updated] = await db
      .update(ctiSitesTable)
      .set({
        legalEntityId: body.data.decision === "reject" ? null : entity.id,
        entityLinkStatus: linkStatus,
        updatedAt: new Date(),
      })
      .where(eq(ctiSitesTable.id, site.id))
      .returning();
    await recordActivity(req, `Entity association ${body.data.decision}d`, "site", site.id, site.domain);
    res.json(LinkSiteEntityResponse.parse(await mapSite(updated)));
  },
);

router.get("/entities", async (req, res): Promise<void> => {
  const parsed = ListEntitiesQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  const rows = await db
    .select()
    .from(ctiEntitiesTable)
    .where(
      parsed.data.q
        ? or(ilike(ctiEntitiesTable.name, `%${parsed.data.q}%`), ilike(ctiEntitiesTable.registrationId, `%${parsed.data.q}%`))
        : undefined,
    )
    .orderBy(desc(ctiEntitiesTable.createdAt));
  const items = rows.map((row) => ({ ...row, createdAt: row.createdAt.toISOString() }));
  res.json(ListEntitiesResponse.parse({ items, total: items.length }));
});

router.post(
  "/entities",
  requireRole(...analystRoles),
  async (req, res): Promise<void> => {
    const parsed = CreateEntityBody.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: parsed.error.message });
      return;
    }
    const [created] = await db
      .insert(ctiEntitiesTable)
      .values({ ...parsed.data, createdBy: "anonymous" })
      .returning();
    await recordActivity(req, "Created legal-entity candidate", "entity", created.id, created.name);
    res.status(201).json(
      CreateEntityResponse.parse({ ...created, createdAt: created.createdAt.toISOString() }),
    );
  },
);

router.get("/events", async (req, res): Promise<void> => {
  const parsed = ListEventsQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  const filters = [];
  if (parsed.data.q) {
    const pattern = `%${parsed.data.q}%`;
    filters.push(
      or(
        ilike(ctiEventsTable.competition, pattern),
        ilike(ctiEventsTable.home, pattern),
        ilike(ctiEventsTable.away, pattern),
      )!,
    );
  }
  if (parsed.data.riskBand) filters.push(eq(ctiEventsTable.riskBand, parsed.data.riskBand));
  const rows = await db
    .select()
    .from(ctiEventsTable)
    .where(filters.length ? and(...filters) : undefined)
    .orderBy(desc(ctiEventsTable.startsAt));
  const items = rows.map(mapEvent);
  res.json(ListEventsResponse.parse({ items, total: items.length }));
});

router.post(
  "/events",
  requireRole(...analystRoles),
  async (req, res): Promise<void> => {
    const parsed = CreateEventBody.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: parsed.error.message });
      return;
    }
    const [created] = await db
      .insert(ctiEventsTable)
      .values({
        ...parsed.data,
        startsAt: new Date(parsed.data.startsAt),
        marketVolume:
          parsed.data.marketVolume == null ? null : String(parsed.data.marketVolume),
        createdBy: "anonymous",
      })
      .returning();
    await recordActivity(req, "Registered sports event", "event", created.id, `${created.home} - ${created.away}`);
    res.status(201).json(CreateEventResponse.parse(mapEvent(created)));
  },
);

router.get("/events/:id", async (req, res): Promise<void> => {
  const params = GetEventParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  const [row] = await db.select().from(ctiEventsTable).where(eq(ctiEventsTable.id, params.data.id)).limit(1);
  if (!row) {
    res.status(404).json({ error: "Event not found" });
    return;
  }
  res.json(GetEventResponse.parse(mapEvent(row)));
});

router.patch(
  "/events/:id",
  requireRole(...analystRoles),
  async (req, res): Promise<void> => {
    const params = UpdateEventParams.safeParse(req.params);
    const body = UpdateEventBody.safeParse(req.body);
    if (!params.success || !body.success) {
      res.status(400).json({ error: params.error?.message ?? body.error?.message });
      return;
    }
    const { marketVolume, ...eventFields } = body.data;
    const updateData = {
      ...eventFields,
      ...(eventFields.startsAt ? { startsAt: new Date(eventFields.startsAt) } : {}),
      ...(marketVolume !== undefined
        ? { marketVolume: marketVolume == null ? null : String(marketVolume) }
        : {}),
    };
    const [updated] = await db
      .update(ctiEventsTable)
      .set(updateData)
      .where(eq(ctiEventsTable.id, params.data.id))
      .returning();
    if (!updated) {
      res.status(404).json({ error: "Event not found" });
      return;
    }
    await recordActivity(req, "Updated event data", "event", updated.id, `${updated.home} - ${updated.away}`);
    res.json(UpdateEventResponse.parse(mapEvent(updated)));
  },
);

router.post(
  "/events/:id/rate",
  requireRole(...analystRoles),
  async (req, res): Promise<void> => {
    const params = RateEventParams.safeParse(req.params);
    const body = RateEventBody.safeParse(req.body);
    if (!params.success || !body.success) {
      res.status(400).json({ error: params.error?.message ?? body.error?.message });
      return;
    }
    const rating = calculateEventRisk(body.data);
    const [updated] = await db
      .update(ctiEventsTable)
      .set({
        oddsSources: body.data.oddsSources,
        marketVolume: String(body.data.marketVolume),
        unusualOdds: body.data.unusualOdds,
        riskBand: rating.riskBand,
        ratingNote: `${body.data.rationale} — ${rating.note}`,
        ratingDetails: { ...rating.details, score: rating.score, dataBasis: body.data.dataBasis },
        updatedAt: new Date(),
      })
      .where(eq(ctiEventsTable.id, params.data.id))
      .returning();
    if (!updated) {
      res.status(404).json({ error: "Event not found" });
      return;
    }
    await recordActivity(req, `Rated event ${rating.riskBand}`, "event", updated.id, `${updated.home} - ${updated.away}`);
    res.json(RateEventResponse.parse(mapEvent(updated)));
  },
);

router.get(
  "/bettors",
  requireRole(...restrictedRoles),
  async (req, res): Promise<void> => {
    const parsed = ListBettorsQueryParams.safeParse(req.query);
    if (!parsed.success) {
      res.status(400).json({ error: parsed.error.message });
      return;
    }
    const rows = await db
      .select()
      .from(ctiBettorsTable)
      .where(
        parsed.data.q
          ? or(ilike(ctiBettorsTable.pseudonymousId, `%${parsed.data.q}%`), ilike(ctiBettorsTable.operator, `%${parsed.data.q}%`))
          : undefined,
      )
      .orderBy(desc(ctiBettorsTable.createdAt));
    const items = rows.map(mapBettor);
    res.json(ListBettorsResponse.parse({ items, total: items.length }));
  },
);

router.post(
  "/bettors",
  requireRole(...restrictedRoles),
  async (req, res): Promise<void> => {
    const parsed = CreateBettorBody.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: parsed.error.message });
      return;
    }
    const [created] = await db
      .insert(ctiBettorsTable)
      .values({
        ...parsed.data,
        averageBet: String(parsed.data.averageBet),
        grossWinnings: String(parsed.data.grossWinnings),
        winRate: String(parsed.data.winRate),
        periodStart: toSqlDate(parsed.data.periodStart)!,
        periodEnd: toSqlDate(parsed.data.periodEnd)!,
        createdBy: "anonymous",
      })
      .returning();
    await recordActivity(req, "Added pseudonymous bettor profile", "bettor", created.id, created.pseudonymousId);
    res.status(201).json(CreateBettorResponse.parse(mapBettor(created)));
  },
);

router.get("/trust/matrix", (_req, res): void => {
  res.json(
    GetTrustMatrixResponse.parse({
      vulnerabilityFactors: trustFactorDefinitions,
      vulnerabilityBands: [
        { label: "low", min: 0, max: 6 },
        { label: "medium", min: 6, max: 12 },
        { label: "high", min: 12, max: null },
      ],
      threatBands: [
        { label: "low", min: 3, max: 4 },
        { label: "medium", min: 4, max: 7 },
        { label: "high", min: 7, max: null },
      ],
      trustIndexBands: [
        { label: "low", min: 0, max: 33 },
        { label: "medium", min: 33, max: 67 },
        { label: "high", min: 67, max: 100 },
      ],
      calibrationNotice: trustCalibrationNotice,
    }),
  );
});

router.get("/trust/scores", async (req, res): Promise<void> => {
  const parsed = ListTrustScoresQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  const rows = await db
    .select()
    .from(ctiTrustScoresTable)
    .where(parsed.data.siteId ? eq(ctiTrustScoresTable.siteId, parsed.data.siteId) : undefined)
    .orderBy(desc(ctiTrustScoresTable.computedAt));
  const items = rows.map(mapTrustScore);
  res.json(ListTrustScoresResponse.parse({ items, total: items.length }));
});

router.post(
  "/trust/scores/calculate",
  requireRole(...analystRoles),
  async (req, res): Promise<void> => {
    const parsed = CalculateTrustScoreBody.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: parsed.error.message });
      return;
    }
    const input = parsed.data;
    const keys = input.vulnerabilityFactors.map((factor) => factor.key);
    const expected = trustFactorDefinitions.map((factor) => factor.key);
    if (
      new Set(keys).size !== expected.length ||
      expected.some((key) => !keys.includes(key))
    ) {
      res.status(400).json({ error: "Provide each of the seven vulnerability factors exactly once" });
      return;
    }
    const [site] = await db.select().from(ctiSitesTable).where(eq(ctiSitesTable.id, input.siteId)).limit(1);
    if (!site) {
      res.status(404).json({ error: "Site not found" });
      return;
    }
    const calculated = calculateTrust(input.vulnerabilityFactors, input.threatMetrics);
    const [created] = await db
      .insert(ctiTrustScoresTable)
      .values({
        siteId: site.id,
        ...calculated,
        vulnerabilityScore: String(calculated.vulnerabilityScore),
        normalizedVulnerability: String(calculated.normalizedVulnerability),
        normalizedThreat: String(calculated.normalizedThreat),
        trustIndex: String(calculated.trustIndex),
        analystNote: input.analystNote,
        createdBy: "anonymous",
      })
      .returning();
    await db
      .update(ctiSitesTable)
      .set({
        trustIndex: String(calculated.trustIndex),
        riskBand: calculated.trustBand,
        updatedAt: new Date(),
      })
      .where(eq(ctiSitesTable.id, site.id));
    await recordActivity(req, `Calculated Trust Index ${calculated.trustBand}`, "site", site.id, site.domain);
    res.status(201).json(CalculateTrustScoreResponse.parse(mapTrustScore(created)));
  },
);

export default router;
