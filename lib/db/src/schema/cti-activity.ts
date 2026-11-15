import { createInsertSchema } from "drizzle-zod";
import { pgTable, serial, text, timestamp } from "drizzle-orm/pg-core";
import { z } from "zod/v4";

export const ctiActivityTable = pgTable("cti_activity", {
  id: serial("id").primaryKey(),
  action: text("action").notNull(),
  entityType: text("entity_type").notNull(),
  entityId: text("entity_id").notNull(),
  entityLabel: text("entity_label").notNull(),
  actorId: text("actor_id").notNull(),
  actorLabel: text("actor_label").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const insertCtiActivitySchema = createInsertSchema(ctiActivityTable).omit({
  id: true,
  createdAt: true,
});
export type InsertCtiActivity = z.infer<typeof insertCtiActivitySchema>;
export type CtiActivity = typeof ctiActivityTable.$inferSelect;
