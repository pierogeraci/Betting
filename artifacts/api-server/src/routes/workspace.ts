import { and, desc, eq, sql } from "drizzle-orm";
import { Router, type IRouter } from "express";
import {
  GetDashboardSummaryResponse,
  ListActivityQueryParams,
  ListActivityResponse,
  ListUsersResponse,
  UpdateUserRoleBody,
  UpdateUserRoleParams,
  UpdateUserRoleResponse,
} from "@workspace/api-zod";
import {
  db,
  ctiActivityTable,
  ctiBettorsTable,
  ctiEvidenceTable,
  ctiEventsTable,
  ctiSitesTable,
  ctiSourcesTable,
  ctiUsersTable,
} from "@workspace/db";
import { requireRole } from "../lib/auth";
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
        createdAt: item.createdAt.toISOString(),
      })),
      total: items.length,
    }),
  );
});

router.get("/users", requireRole("admin"), async (_req, res): Promise<void> => {
  const users = await db.select().from(ctiUsersTable).orderBy(desc(ctiUsersTable.createdAt));
  res.json(
    ListUsersResponse.parse({
      items: users.map((user) => ({ ...user, createdAt: user.createdAt.toISOString() })),
      total: users.length,
    }),
  );
});

router.patch(
  "/users/:userId/role",
  requireRole("admin"),
  async (req, res): Promise<void> => {
    const params = UpdateUserRoleParams.safeParse(req.params);
    const body = UpdateUserRoleBody.safeParse(req.body);
    if (!params.success || !body.success) {
      res.status(400).json({ error: params.error?.message ?? body.error?.message });
      return;
    }
    const targetId = params.data.userId;
    if (req.ctiUser?.id === targetId && body.data.role !== "admin") {
      res.status(400).json({ error: "An administrator cannot remove their own admin role" });
      return;
    }
    const [target] = await db
      .select()
      .from(ctiUsersTable)
      .where(eq(ctiUsersTable.id, targetId))
      .limit(1);
    if (!target) {
      res.status(404).json({ error: "Workspace member not found" });
      return;
    }
    if (target.role === "admin" && body.data.role !== "admin") {
      const [adminCount] = await db
        .select({ count: sql<number>`count(*)::int` })
        .from(ctiUsersTable)
        .where(and(eq(ctiUsersTable.role, "admin"), eq(ctiUsersTable.status, "active")));
      if (Number(adminCount?.count ?? 0) <= 1) {
        res.status(400).json({ error: "The last active administrator cannot be demoted" });
        return;
      }
    }
    const [updated] = await db
      .update(ctiUsersTable)
      .set({
        role: body.data.role,
        status: target.status === "pending" ? "active" : target.status,
        updatedAt: new Date(),
      })
      .where(eq(ctiUsersTable.id, targetId))
      .returning();
    await recordActivity(
      req,
      `Assigned role ${body.data.role}`,
      "user",
      targetId,
      target.displayName,
    );
    res.json(
      UpdateUserRoleResponse.parse({
        ...updated,
        createdAt: updated.createdAt.toISOString(),
      }),
    );
  },
);

export default router;
