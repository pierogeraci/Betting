import { desc, eq, ilike, or } from "drizzle-orm";
import { Router, type IRouter } from "express";
import {
  CreateSourceBody,
  CreateSourceResponse,
  GetSourceParams,
  GetSourceResponse,
  ListSourcesQueryParams,
  ListSourcesResponse,
  ReviewSourceBody,
  ReviewSourceParams,
  ReviewSourceResponse,
  UpdateSourceBody,
  UpdateSourceParams,
  UpdateSourceResponse,
} from "@workspace/api-zod";
import { db, ctiSourcesTable } from "@workspace/db";
import { requireRole } from "../lib/auth";
import { isSafeObjectPath, recordActivity, serializeSource, toSqlDate } from "../lib/cti-utils";

const router: IRouter = Router();
const adminRoles = ["admin", "analyst"] as const;
const reviewRoles = ["admin", "compliance_reviewer"] as const;

function validSecretReference(value: string | undefined) {
  return !value || /^(vault|env|replit):[A-Za-z0-9_./-]{1,180}$/.test(value);
}

router.get("/sources", async (req, res): Promise<void> => {
  const parsed = ListSourcesQueryParams.safeParse(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }
  const { q, legalStatus, connectorStatus } = parsed.data;
  const filters = [];
  if (q) {
    const pattern = `%${q}%`;
    filters.push(
      or(
        ilike(ctiSourcesTable.name, pattern),
        ilike(ctiSourcesTable.provider, pattern),
        ilike(ctiSourcesTable.owner, pattern),
        ilike(ctiSourcesTable.category, pattern),
      )!,
    );
  }
  if (legalStatus) filters.push(eq(ctiSourcesTable.legalStatus, legalStatus));
  if (connectorStatus) filters.push(eq(ctiSourcesTable.connectorStatus, connectorStatus));
  const query = db.select().from(ctiSourcesTable);
  const rows = filters.length
    ? await query.where(filters.length === 1 ? filters[0] : or(...filters)).orderBy(desc(ctiSourcesTable.updatedAt))
    : await query.orderBy(desc(ctiSourcesTable.updatedAt));
  const items = rows.map(serializeSource);
  res.json(ListSourcesResponse.parse({ items, total: items.length }));
});

router.post(
  "/sources",
  requireRole(...adminRoles),
  async (req, res): Promise<void> => {
    const parsed = CreateSourceBody.safeParse(req.body);
    if (!parsed.success) {
      res.status(400).json({ error: parsed.error.message });
      return;
    }
    const input = parsed.data;
    if (!validSecretReference(input.secretReference)) {
      res.status(400).json({
        error: "Enter a vault reference only, never a credential or secret value",
      });
      return;
    }
    if (input.authorizationEvidencePath && !isSafeObjectPath(input.authorizationEvidencePath)) {
      res.status(400).json({ error: "Authorization evidence path is invalid" });
      return;
    }
    const [created] = await db
      .insert(ctiSourcesTable)
      .values({
        ...input,
        validFrom: toSqlDate(input.validFrom)!,
        validUntil: toSqlDate(input.validUntil),
        legalStatus: "draft",
        connectorStatus: "not_configured",
        createdBy: req.ctiUser!.clerkUserId,
      })
      .returning();
    await recordActivity(req, "Registered source for review", "source", created.id, created.name);
    res.status(201).json(CreateSourceResponse.parse(serializeSource(created)));
  },
);

router.get("/sources/:id", async (req, res): Promise<void> => {
  const params = GetSourceParams.safeParse(req.params);
  if (!params.success) {
    res.status(400).json({ error: params.error.message });
    return;
  }
  const [source] = await db
    .select()
    .from(ctiSourcesTable)
    .where(eq(ctiSourcesTable.id, params.data.id))
    .limit(1);
  if (!source) {
    res.status(404).json({ error: "Source not found" });
    return;
  }
  res.json(GetSourceResponse.parse(serializeSource(source)));
});

router.patch(
  "/sources/:id",
  requireRole(...adminRoles),
  async (req, res): Promise<void> => {
    const params = UpdateSourceParams.safeParse(req.params);
    const body = UpdateSourceBody.safeParse(req.body);
    if (!params.success || !body.success) {
      res.status(400).json({ error: params.error?.message ?? body.error?.message });
      return;
    }
    const input = body.data;
    if (!validSecretReference(input.secretReference)) {
      res.status(400).json({
        error: "Enter a vault reference only, never a credential or secret value",
      });
      return;
    }
    if (input.authorizationEvidencePath && !isSafeObjectPath(input.authorizationEvidencePath)) {
      res.status(400).json({ error: "Authorization evidence path is invalid" });
      return;
    }
    const { validFrom, validUntil, ...sourceFields } = input;
    const updateData = {
      ...sourceFields,
      ...(validFrom !== undefined ? { validFrom: toSqlDate(validFrom)! } : {}),
      ...(validUntil !== undefined ? { validUntil: toSqlDate(validUntil) } : {}),
    };
    const [updated] = await db
      .update(ctiSourcesTable)
      .set({ ...updateData, updatedAt: new Date() })
      .where(eq(ctiSourcesTable.id, params.data.id))
      .returning();
    if (!updated) {
      res.status(404).json({ error: "Source not found" });
      return;
    }
    await recordActivity(req, "Updated source authorization record", "source", updated.id, updated.name);
    res.json(UpdateSourceResponse.parse(serializeSource(updated)));
  },
);

router.post(
  "/sources/:id/review",
  requireRole(...reviewRoles),
  async (req, res): Promise<void> => {
    const params = ReviewSourceParams.safeParse(req.params);
    const body = ReviewSourceBody.safeParse(req.body);
    if (!params.success || !body.success) {
      res.status(400).json({ error: params.error?.message ?? body.error?.message });
      return;
    }
    const [source] = await db
      .select()
      .from(ctiSourcesTable)
      .where(eq(ctiSourcesTable.id, params.data.id))
      .limit(1);
    if (!source) {
      res.status(404).json({ error: "Source not found" });
      return;
    }
    const decisionToStatus = {
      approve: "approved",
      reject: "rejected",
      suspend: "suspended",
      revoke: "revoked",
    } as const;
    if (
      body.data.decision === "approve" &&
      source.validUntil &&
      source.validUntil < new Date().toISOString().slice(0, 10)
    ) {
      res.status(400).json({ error: "An expired source authorization cannot be approved" });
      return;
    }
    const [updated] = await db
      .update(ctiSourcesTable)
      .set({
        legalStatus: decisionToStatus[body.data.decision],
        reviewNote: body.data.reason,
        reviewerId: req.ctiUser!.clerkUserId,
        updatedAt: new Date(),
      })
      .where(eq(ctiSourcesTable.id, source.id))
      .returning();
    const actionLabel = {
      approve: "approved",
      reject: "rejected",
      suspend: "suspended",
      revoke: "revoked",
    }[body.data.decision];
    await recordActivity(req, `Source authorization ${actionLabel}`, "source", updated.id, updated.name);
    res.json(ReviewSourceResponse.parse(serializeSource(updated)));
  },
);

export default router;
