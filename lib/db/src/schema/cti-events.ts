import { createInsertSchema } from "drizzle-zod";
import { boolean, integer, jsonb, pgTable, serial, text, timestamp, numeric } from "drizzle-orm/pg-core";
import { z } from "zod/v4";

export const ctiEventsTable = pgTable("cti_events", {
  id: serial("id").primaryKey(),
  sport: text("sport").notNull(),
  competition: text("competition").notNull(),
  home: text("home").notNull(),
  away: text("away").notNull(),
  startsAt: timestamp("starts_at", { withTimezone: true }).notNull(),
  oddsSources: integer("odds_sources").notNull().default(0),
  marketVolume: numeric("market_volume", { precision: 16, scale: 2 }),
  unusualOdds: boolean("unusual_odds"),
  riskBand: text("risk_band").notNull().default("unassessed"),
  ratingNote: text("rating_note").notNull().default(""),
  ratingDetails: jsonb("rating_details").$type<Record<string, unknown>>().notNull().default({}),
  synthetic: boolean("synthetic").notNull().default(false),
  createdBy: text("created_by").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow().$onUpdate(() => new Date()),
});

export const insertCtiEventSchema = createInsertSchema(ctiEventsTable).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});
export type InsertCtiEvent = z.infer<typeof insertCtiEventSchema>;
export type CtiEvent = typeof ctiEventsTable.$inferSelect;
