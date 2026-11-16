import { Router, type IRouter } from "express";
import { eq, sql } from "drizzle-orm";
import {
  GetLocalSessionResponse,
  LoginLocalUserBody,
  LoginLocalUserResponse,
} from "@workspace/api-zod";
import { ctiUsersTable, db } from "@workspace/db";
import {
  createSessionToken,
  getSessionSecret,
  hashPassword,
  isValidUserId,
  normalizeUserId,
  SESSION_COOKIE_NAME,
  SESSION_LIFETIME_SECONDS,
  verifyPassword,
  verifySessionToken,
} from "../lib/local-auth-crypto";

const router: IRouter = Router();
const failedAttempts = new Map<string, { count: number; windowStart: number }>();
const ATTEMPT_WINDOW_MS = 15 * 60 * 1000;
const MAX_ATTEMPTS = 10;

function makeSessionUser(member: typeof ctiUsersTable.$inferSelect) {
  return {
    userId: member.userId!,
    displayName: member.displayName,
    role: member.role,
    status: member.status,
  };
}

async function readActiveMember(cookie: string | undefined) {
  let session: ReturnType<typeof verifySessionToken>;
  try {
    session = verifySessionToken(cookie);
  } catch {
    return null;
  }
  if (!session) return null;

  const [member] = await db
    .select()
    .from(ctiUsersTable)
    .where(eq(ctiUsersTable.id, session.userId))
    .limit(1);
  return member?.userId &&
    member.status === "active" &&
    member.sessionVersion === session.sessionVersion
    ? member
    : null;
}

router.get("/auth/session", async (req, res): Promise<void> => {
  const member = await readActiveMember(req.cookies?.[SESSION_COOKIE_NAME]);
  res.json(
    GetLocalSessionResponse.parse({
      authenticated: Boolean(member),
      user: member ? makeSessionUser(member) : null,
    }),
  );
});

router.post("/auth/login", async (req, res): Promise<void> => {
  const parsed = LoginLocalUserBody.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: "Inserisci un ID utente e una password validi." });
    return;
  }

  const userId = normalizeUserId(parsed.data.userId);
  if (!isValidUserId(userId)) {
    res.status(401).json({ error: "ID utente o password non corretti." });
    return;
  }
  const now = Date.now();
  if (failedAttempts.size > 2_000) {
    for (const [key, record] of failedAttempts) {
      if (now - record.windowStart >= ATTEMPT_WINDOW_MS) failedAttempts.delete(key);
    }
    while (failedAttempts.size > 2_000) {
      const oldestKey = failedAttempts.keys().next().value;
      if (!oldestKey) break;
      failedAttempts.delete(oldestKey);
    }
  }
  const attemptKey = `${req.ip || "unknown"}:${userId}`;
  const attempt = failedAttempts.get(attemptKey);
  if (attempt && now - attempt.windowStart < ATTEMPT_WINDOW_MS && attempt.count >= MAX_ATTEMPTS) {
    res.status(429).json({ error: "Troppi tentativi. Attendi qualche minuto e riprova." });
    return;
  }

  const [member] = await db
    .select()
    .from(ctiUsersTable)
    .where(eq(ctiUsersTable.userId, userId))
    .limit(1);
  const passwordMatches = member?.passwordHash
    ? await verifyPassword(parsed.data.password, member.passwordHash)
    : (await hashPassword(parsed.data.password), false);

  if (!member || !passwordMatches || member.status !== "active") {
    const current = attempt && now - attempt.windowStart < ATTEMPT_WINDOW_MS
      ? attempt
      : { count: 0, windowStart: now };
    failedAttempts.set(attemptKey, { ...current, count: current.count + 1 });
    res.status(401).json({ error: "ID utente o password non corretti." });
    return;
  }

  failedAttempts.delete(attemptKey);
  const token = createSessionToken(member.id, member.sessionVersion);
  res.cookie(SESSION_COOKIE_NAME, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    maxAge: SESSION_LIFETIME_SECONDS * 1000,
    path: "/",
  });
  res.json(
    LoginLocalUserResponse.parse({
      authenticated: true,
      user: makeSessionUser(member),
    }),
  );
});

router.post("/auth/logout", async (req, res): Promise<void> => {
  let session: ReturnType<typeof verifySessionToken> = null;
  try {
    session = verifySessionToken(req.cookies?.[SESSION_COOKIE_NAME]);
  } catch {
    session = null;
  }
  if (session) {
    await db
      .update(ctiUsersTable)
      .set({ sessionVersion: sql`${ctiUsersTable.sessionVersion} + 1` })
      .where(eq(ctiUsersTable.id, session.userId));
  }
  res.clearCookie(SESSION_COOKIE_NAME, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
  });
  res.sendStatus(204);
});

export default router;
