import { createInsertSchema } from "drizzle-zod";
import { date, numeric, pgTable, serial, text, timestamp, boolean } from "drizzle-orm/pg-core";
import { z } from "zod/v4";

export const ctiBettorsTable = pgTable("cti_bettors", {
  id: serial("id").primaryKey(),
  pseudonymousId: text("pseudonymous_id").notNull(),
  operator: text("operator").notNull(),
  periodStart: date("period_start", { mode: "string" }).notNull(),
  periodEnd: date("period_end", { mode: "string" }).notNull(),
  averageBet: numeric("average_bet", { precision: 16, scale: 2 }).notNull(),
  grossWinnings: numeric("gross_winnings", { precision: 16, scale: 2 }).notNull(),
  winRate: numeric("win_rate", { precision: 6, scale: 5 }).notNull(),
  dataBasis: text("data_basis").notNull(),
  synthetic: boolean("synthetic").notNull().default(false),
  riskNote: text("risk_note").notNull().default(""),
  createdBy: text("created_by").notNull(),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const insertCtiBettorSchema = createInsertSchema(ctiBettorsTable).omit({
  id: true,
  createdAt: true,
});
export type InsertCtiBettor = z.infer<typeof insertCtiBettorSchema>;
export type CtiBettor = typeof ctiBettorsTable.$inferSelect;
