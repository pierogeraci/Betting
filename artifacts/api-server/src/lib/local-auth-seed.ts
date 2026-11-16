import { eq, isNotNull } from "drizzle-orm";
import { ctiUsersTable, db } from "@workspace/db";
import {
  hashPassword,
  isValidUserId,
  normalizeUserId,
} from "./local-auth-crypto";

export async function seedInitialLocalAdmin(): Promise<boolean> {
  const rawUserId = process.env.LOCAL_AUTH_ADMIN_USER_ID;
  const password = process.env.LOCAL_AUTH_ADMIN_PASSWORD;

  if (!rawUserId && !password) return false;
  if (!rawUserId || !password) {
    throw new Error(
      "LOCAL_AUTH_ADMIN_USER_ID and LOCAL_AUTH_ADMIN_PASSWORD must be configured together.",
    );
  }

  const userId = normalizeUserId(rawUserId);
  if (!isValidUserId(userId)) {
    throw new Error("LOCAL_AUTH_ADMIN_USER_ID has an invalid format.");
  }
  if (password.length < 12 || password.length > 256) {
    throw new Error("LOCAL_AUTH_ADMIN_PASSWORD must be 12–256 characters long.");
  }

  const [existingLocalUser] = await db
    .select({ id: ctiUsersTable.id })
    .from(ctiUsersTable)
    .where(isNotNull(ctiUsersTable.userId))
    .limit(1);
  if (existingLocalUser) return false;

  const legacyId = `local:${userId}`;
  const [legacyCollision] = await db
    .select({ id: ctiUsersTable.id })
    .from(ctiUsersTable)
    .where(eq(ctiUsersTable.clerkUserId, legacyId))
    .limit(1);
  if (legacyCollision) {
    throw new Error("The configured local user ID conflicts with an existing account.");
  }

  await db.insert(ctiUsersTable).values({
    clerkUserId: legacyId,
    userId,
    passwordHash: await hashPassword(password),
    displayName: userId,
    email: null,
    role: "admin",
    status: "active",
  });
  return true;
}
