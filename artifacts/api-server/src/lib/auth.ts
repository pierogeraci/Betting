import { getAuth } from "@clerk/express";
import { eq, sql } from "drizzle-orm";
import type { NextFunction, Request, Response } from "express";
import {
  db,
  ctiSourcesTable,
  ctiUsersTable,
  type CtiUser,
} from "@workspace/db";

type WorkspaceRole =
  | "admin"
  | "analyst"
  | "compliance_reviewer"
  | "restricted_analyst"
  | "read_only";

declare global {
  namespace Express {
    interface Request {
      ctiUser?: CtiUser;
    }
  }
}

const roleSet = new Set<WorkspaceRole>([
  "admin",
  "analyst",
  "compliance_reviewer",
  "restricted_analyst",
  "read_only",
]);

function getIdentity(req: Request) {
  const auth = getAuth(req);
  const claimUserId = auth?.sessionClaims?.userId;
  const userId =
    typeof claimUserId === "string"
      ? claimUserId
      : typeof auth?.userId === "string"
        ? auth.userId
        : null;
  if (!userId) return null;

  const claims = auth.sessionClaims as Record<string, unknown> | null;
  const name =
    typeof claims?.name === "string" && claims.name.trim()
      ? claims.name.trim()
      : `Analyst ${userId.slice(-6)}`;
  const email =
    typeof claims?.email === "string"
      ? claims.email
      : typeof claims?.email_address === "string"
        ? claims.email_address
        : null;
  return { userId, name, email };
}

async function getOrCreateAppUser(req: Request): Promise<CtiUser | null> {
  const identity = getIdentity(req);
  if (!identity) return null;

  const [existing] = await db
    .select()
    .from(ctiUsersTable)
    .where(eq(ctiUsersTable.clerkUserId, identity.userId))
    .limit(1);
  if (existing) return existing;

  const [countRow] = await db
    .select({ count: sql<number>`count(*)::int` })
    .from(ctiUsersTable);
  const configuredAdmins = (process.env.CTI_BOOTSTRAP_ADMIN_IDS ?? "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  const firstDevelopmentAdmin =
    process.env.NODE_ENV !== "production" && Number(countRow?.count ?? 0) === 0;
  const isConfiguredAdmin = configuredAdmins.includes(identity.userId);
  const role: WorkspaceRole =
    firstDevelopmentAdmin || isConfiguredAdmin ? "admin" : "read_only";
  const status = firstDevelopmentAdmin || isConfiguredAdmin ? "active" : "pending";

  const [created] = await db
    .insert(ctiUsersTable)
    .values({
      clerkUserId: identity.userId,
      displayName: identity.name,
      email: identity.email,
      role,
      status,
    })
    .onConflictDoNothing({ target: ctiUsersTable.clerkUserId })
    .returning();
  if (created) return created;

  const [raced] = await db
    .select()
    .from(ctiUsersTable)
    .where(eq(ctiUsersTable.clerkUserId, identity.userId))
    .limit(1);
  return raced ?? null;
}

export async function requireSignedIn(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  if (!getIdentity(req)) {
    res.status(401).json({ error: "Sign-in required" });
    return;
  }
  next();
}

export async function loadWorkspaceUser(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  try {
    const user = await getOrCreateAppUser(req);
    if (!user) {
      res.status(401).json({ error: "Sign-in required" });
      return;
    }
    req.ctiUser = user;
    next();
  } catch (error) {
    req.log.error({ err: error }, "Could not load workspace identity");
    res.status(500).json({ error: "Could not load workspace identity" });
  }
}

export async function requireActiveMember(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  try {
    const user = await getOrCreateAppUser(req);
    if (!user) {
      res.status(401).json({ error: "Sign-in required" });
      return;
    }
    req.ctiUser = user;
    if (user.status !== "active") {
      res.status(403).json({
        error: "Workspace access is pending administrator approval",
      });
      return;
    }
    next();
  } catch (error) {
    req.log.error({ err: error }, "Could not verify workspace access");
    res.status(500).json({ error: "Could not verify workspace access" });
  }
}

export function requireRole(...roles: WorkspaceRole[]) {
  const allowed = roles.filter((role) => roleSet.has(role));
  return (req: Request, res: Response, next: NextFunction): void => {
    if (!req.ctiUser || !allowed.includes(req.ctiUser.role as WorkspaceRole)) {
      res.status(403).json({ error: "This role cannot perform this action" });
      return;
    }
    next();
  };
}

export function currentIdentity(req: Request) {
  return getIdentity(req);
}

export async function getSessionUser(req: Request): Promise<CtiUser | null> {
  return getOrCreateAppUser(req);
}

export async function findActiveSource(sourceId: number) {
  const today = new Date().toISOString().slice(0, 10);
  const [source] = await db
    .select()
    .from(ctiSourcesTable)
    .where(eq(ctiSourcesTable.id, sourceId))
    .limit(1);
  if (!source) return null;
  const status =
    source.legalStatus === "approved" && source.validUntil && source.validUntil < today
      ? "expired"
      : source.legalStatus;
  return status === "approved" && source.validFrom <= today &&
    (!source.validUntil || source.validUntil >= today)
    ? source
    : null;
}
