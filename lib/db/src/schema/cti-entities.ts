import { createInsertSchema } from "drizzle-zod";
import { pgTable, serial, text, timestamp } from "drizzle-orm/pg-core";
import { z } from "zod/v4";

export const ctiEntitiesTable = pgTable("cti_entities", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  entityType: text("entity_type").notNull().default("unknown"),
  country: text("country").notNull().default(""),
  registrationId: text("registration_id").notNull().default(""),
  evidenceNotes: text("evidence_notes").notNull().default(""),
  createdBy: text("created_by").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const insertCtiEntitySchema = createInsertSchema(ctiEntitiesTable).omit({
  id: true,
  createdAt: true,
});
export type InsertCtiEntity = z.infer<typeof insertCtiEntitySchema>;
export type CtiEntity = typeof ctiEntitiesTable.$inferSelect;
