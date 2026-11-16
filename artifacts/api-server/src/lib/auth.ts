import type { NextFunction, Request, Response } from "express";
import { getAuth } from "@clerk/express";
import { eq } from "drizzle-orm";
import { ctiUsersTable, db } from "@workspace/db";
import { hasActiveRole } from "./permissions";

export function requireAuthenticated(
  req: Request,
  res: Response,
  next: NextFunction,
): void {
  const { userId } = getAuth(req);
  if (!userId) {
    res.status(401).json({ error: "È necessario accedere alla piattaforma." });
    return;
  }
  next();
}

export function requireRole(...roles: string[]) {
  return async (req: Request, res: Response, next: NextFunction): Promise<void> => {
    const { userId } = getAuth(req);
    if (!userId) {
      res.status(401).json({ error: "È necessario accedere alla piattaforma." });
      return;
    }

    const [member] = await db
      .select()
      .from(ctiUsersTable)
      .where(eq(ctiUsersTable.clerkUserId, userId))
      .limit(1);

    if (!member) {
      res.status(403).json({
        error: "L’accesso ai dati riservati richiede un membro attivo della piattaforma.",
      });
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
