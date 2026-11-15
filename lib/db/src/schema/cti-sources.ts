import { createInsertSchema } from "drizzle-zod";
import { date, integer, jsonb, pgTable, serial, text, timestamp } from "drizzle-orm/pg-core";
import { z } from "zod/v4";

export const ctiSourcesTable = pgTable("cti_sources", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  provider: text("provider").notNull(),
  url: text("url"),
  category: text("category").notNull(),
  accessMethod: text("access_method").notNull(),
  owner: text("owner").notNull(),
  purpose: text("purpose").notNull(),
  scope: text("scope").notNull(),
  dataCategories: jsonb("data_categories").$type<string[]>().notNull().default([]),
  authorizationBasis: text("authorization_basis").notNull(),
  authorizationEvidenceName: text("authorization_evidence_name"),
  authorizationEvidencePath: text("authorization_evidence_path"),
  validFrom: date("valid_from", { mode: "string" }).notNull(),
  validUntil: date("valid_until", { mode: "string" }),
  reviewerRole: text("reviewer_role"),
  reviewerId: text("reviewer_id"),
  legalStatus: text("legal_status").notNull().default("draft"),
  connectorStatus: text("connector_status").notNull().default("not_configured"),
  connectorScopes: jsonb("connector_scopes").$type<string[]>().notNull().default([]),
  secretReference: text("secret_reference").notNull().default(""),
  reviewNote: text("review_note"),
  createdBy: text("created_by").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow().$onUpdate(() => new Date()),
});

export const insertCtiSourceSchema = createInsertSchema(ctiSourcesTable).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});
export type InsertCtiSource = z.infer<typeof insertCtiSourceSchema>;
export type CtiSource = typeof ctiSourcesTable.$inferSelect;
