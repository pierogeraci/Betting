import { createInsertSchema } from "drizzle-zod";
import { integer, numeric, pgTable, serial, text, timestamp, uniqueIndex } from "drizzle-orm/pg-core";
import { z } from "zod/v4";

export const ctiSitesTable = pgTable(
  "cti_sites",
  {
    id: serial("id").primaryKey(),
    domain: text("domain").notNull(),
    name: text("name").notNull(),
    description: text("description").notNull().default(""),
    firstSeenAt: timestamp("first_seen_at", { withTimezone: true }),
    lastSeenAt: timestamp("last_seen_at", { withTimezone: true }),
    jurisdiction: text("jurisdiction").notNull().default(""),
    licenseClaim: text("license_claim").notNull().default(""),
    legalEntityId: integer("legal_entity_id"),
    entityLinkStatus: text("entity_link_status").notNull().default("unlinked"),
    riskBand: text("risk_band").notNull().default("unassessed"),
    trustIndex: numeric("trust_index", { precision: 6, scale: 2 }),
    createdBy: text("created_by").notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow().$onUpdate(() => new Date()),
  },
  (table) => [uniqueIndex("cti_sites_domain_idx").on(table.domain)],
);

export const insertCtiSiteSchema = createInsertSchema(ctiSitesTable).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});
export type InsertCtiSite = z.infer<typeof insertCtiSiteSchema>;
export type CtiSite = typeof ctiSitesTable.$inferSelect;
