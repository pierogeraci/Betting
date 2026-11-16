import { desc } from "drizzle-orm";
import { Router, type IRouter, type Request, type Response, type NextFunction } from "express";
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
import { parseExportQuery } from "../lib/export-query";
import { restrictedBettorExportRoles } from "../lib/permissions";
import { createWorkbook, type WorkbookScope } from "../lib/workbook";

const router: IRouter = Router();
const contentType =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

async function authorizeRestrictedExport(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  const parsed = parseExportQuery(req.query);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.message });
    return;
  }

  const { scope = "all", includeRestricted = false } = parsed.data;
  if (scope === "bettors" && !includeRestricted) {
    res.status(403).json({
      error: "Per esportare i profili scommettitori occorre selezionare l’inclusione esplicita.",
    });
    return;
  }

  if (
    includeRestricted &&
    (scope === "all" || scope === "bettors")
  ) {
    await requireRole(...restrictedBettorExportRoles)(req, res, next);
    return;
  }

  next();
}

router.get(
  "/exports/xlsx",
  authorizeRestrictedExport,
  async (req, res): Promise<void> => {
    const parsed = parseExportQuery(req.query);
    if (!parsed.success) {
      res.status(400).json({ error: parsed.error.message });
      return;
    }

    const { scope = "all" } = parsed.data;
    const includeRestricted =
      parsed.data.includeRestricted &&
      (scope === "all" || scope === "bettors");
    const [
      sources,
      evidence,
      sites,
      entities,
      events,
      scores,
      activity,
      bettors,
    ] = await Promise.all([
      db.select().from(ctiSourcesTable).orderBy(desc(ctiSourcesTable.updatedAt)),
      db.select().from(ctiEvidenceTable).orderBy(desc(ctiEvidenceTable.capturedAt)),
      db.select().from(ctiSitesTable).orderBy(desc(ctiSitesTable.updatedAt)),
      db.select().from(ctiEntitiesTable).orderBy(desc(ctiEntitiesTable.createdAt)),
      db.select().from(ctiEventsTable).orderBy(desc(ctiEventsTable.startsAt)),
      db.select().from(ctiTrustScoresTable).orderBy(desc(ctiTrustScoresTable.computedAt)),
      db.select().from(ctiActivityTable).orderBy(desc(ctiActivityTable.createdAt)),
      includeRestricted
        ? db.select().from(ctiBettorsTable).orderBy(desc(ctiBettorsTable.createdAt))
        : Promise.resolve([]),
    ]);

    const generatedAt = new Date().toISOString();
    const buffer = await createWorkbook(
      scope as WorkbookScope,
      includeRestricted,
      { sources, evidence, sites, entities, events, scores, activity, bettors },
      generatedAt,
    );
    const filename = `estrazione-cti-${new Date().toISOString().slice(0, 10)}.xlsx`;
    res.setHeader("Content-Type", contentType);
    res.setHeader("Content-Disposition", `attachment; filename="${filename}"`);
    res.setHeader("Cache-Control", "no-store");
    res.send(buffer);
  },
);

export default router;
