import { createInsertSchema } from "drizzle-zod";
import { integer, jsonb, numeric, pgTable, serial, text, timestamp } from "drizzle-orm/pg-core";
import { z } from "zod/v4";

export const ctiTrustScoresTable = pgTable("cti_trust_scores", {
  id: serial("id").primaryKey(),
  siteId: integer("site_id").notNull(),
  vulnerabilityScore: numeric("vulnerability_score", { precision: 6, scale: 2 }).notNull(),
  vulnerabilityBand: text("vulnerability_band").notNull(),
  threatScore: integer("threat_score").notNull(),
  threatBand: text("threat_band").notNull(),
  normalizedVulnerability: numeric("normalized_vulnerability", { precision: 6, scale: 2 }).notNull(),
  normalizedThreat: numeric("normalized_threat", { precision: 6, scale: 2 }).notNull(),
  trustIndex: numeric("trust_index", { precision: 6, scale: 2 }).notNull(),
  trustBand: text("trust_band").notNull(),
  factorDetails: jsonb("factor_details").$type<Array<Record<string, unknown>>>().notNull(),
  threatDetails: jsonb("threat_details").$type<Record<string, unknown>>().notNull(),
  analystNote: text("analyst_note").notNull().default(""),
  calibrationNotice: text("calibration_notice").notNull(),
  createdBy: text("created_by").notNull(),
  computedAt: timestamp("computed_at", { withTimezone: true }).notNull().defaultNow(),
});

export const insertCtiTrustScoreSchema = createInsertSchema(ctiTrustScoresTable).omit({
  id: true,
  computedAt: true,
});
export type InsertCtiTrustScore = z.infer<typeof insertCtiTrustScoreSchema>;
export type CtiTrustScore = typeof ctiTrustScoresTable.$inferSelect;
