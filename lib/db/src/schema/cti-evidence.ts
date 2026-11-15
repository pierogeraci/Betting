import { createInsertSchema } from "drizzle-zod";
import { boolean, integer, jsonb, pgTable, serial, text, timestamp } from "drizzle-orm/pg-core";
import { z } from "zod/v4";

export const ctiEvidenceTable = pgTable("cti_evidence", {
  id: serial("id").primaryKey(),
  title: text("title").notNull(),
  channel: text("channel").notNull(),
  sourceId: integer("source_id"),
  originalUrl: text("original_url"),
  capturedAt: timestamp("captured_at", { withTimezone: true }).notNull(),
  rawContent: text("raw_content").notNull(),
  categories: jsonb("categories").$type<string[]>().notNull().default([]),
  extractedFacts: jsonb("extracted_facts").$type<Record<string, unknown>>().notNull().default({}),
  normalizedFields: jsonb("normalized_fields").$type<Record<string, unknown>>().notNull().default({}),
  enrichmentNotes: text("enrichment_notes").notNull().default(""),
  status: text("status").notNull().default("new"),
  relatedSiteId: integer("related_site_id"),
  eventId: integer("event_id"),
  entityId: integer("entity_id"),
  attachmentName: text("attachment_name"),
  attachmentPath: text("attachment_path"),
  synthetic: boolean("synthetic").notNull().default(false),
  createdBy: text("created_by").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const insertCtiEvidenceSchema = createInsertSchema(ctiEvidenceTable).omit({
  id: true,
  createdAt: true,
});
export type InsertCtiEvidence = z.infer<typeof insertCtiEvidenceSchema>;
export type CtiEvidence = typeof ctiEvidenceTable.$inferSelect;
