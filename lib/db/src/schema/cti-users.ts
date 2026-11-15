import { createInsertSchema } from "drizzle-zod";
import { pgTable, serial, text, timestamp, uniqueIndex } from "drizzle-orm/pg-core";
import { z } from "zod/v4";

export const ctiUsersTable = pgTable(
  "cti_users",
  {
    id: serial("id").primaryKey(),
    clerkUserId: text("clerk_user_id").notNull(),
    displayName: text("display_name").notNull().default("Workspace member"),
    email: text("email"),
    role: text("role").notNull().default("read_only"),
    status: text("status").notNull().default("pending"),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp("updated_at", { withTimezone: true }).notNull().defaultNow().$onUpdate(() => new Date()),
  },
  (table) => [uniqueIndex("cti_users_clerk_user_id_idx").on(table.clerkUserId)],
);

export const insertCtiUserSchema = createInsertSchema(ctiUsersTable).omit({
  id: true,
  createdAt: true,
  updatedAt: true,
});
export type InsertCtiUser = z.infer<typeof insertCtiUserSchema>;
export type CtiUser = typeof ctiUsersTable.$inferSelect;
