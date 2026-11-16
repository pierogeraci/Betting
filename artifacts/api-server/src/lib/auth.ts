import type { NextFunction, Request, Response } from "express";
import { eq } from "drizzle-orm";
import { ctiUsersTable, db, type CtiUser } from "@workspace/db";
import { hasActiveRole } from "./permissions";
import {
  SESSION_COOKIE_NAME,
  verifySessionToken,
} from "./local-auth-crypto";

declare global {
  namespace Express {
    interface Request {
      ctiUser?: CtiUser;
    }
  }
}

export async function requireAuthenticated(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  let session: ReturnType<typeof verifySessionToken>;
  try {
    session = verifySessionToken(req.cookies?.[SESSION_COOKIE_NAME]);
  } catch {
    session = null;
  }
  if (!session) {
    res.status(401).json({ error: "È necessario accedere alla piattaforma." });
    return;
  }

  const [member] = await db
    .select()
    .from(ctiUsersTable)
    .where(eq(ctiUsersTable.id, session.userId))
    .limit(1);
  if (
    !member?.userId ||
    member.status !== "active" ||
    member.sessionVersion !== session.sessionVersion
  ) {
    res.status(401).json({ error: "La sessione non è valida o l’account non è attivo." });
    return;
  }

  req.ctiUser = member;
  next();
}

export function requireRole(...roles: string[]) {
  return async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    const member = req.ctiUser;
    if (!member) {
      res.status(401).json({ error: "È necessario accedere alla piattaforma." });
      return;
    }

    if (!hasActiveRole(member.role, member.status, roles)) {
      res.status(403).json({
        error: "Il ruolo assegnato non consente questa operazione.",
      });
      return;
    }

    next();
  };
}
