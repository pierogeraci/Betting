import {
  createHmac,
  randomBytes,
  scrypt,
  timingSafeEqual,
} from "node:crypto";

export const SESSION_COOKIE_NAME = "cti_session";
export const SESSION_LIFETIME_SECONDS = 12 * 60 * 60;
const PASSWORD_KEY_LENGTH = 64;

function deriveKey(password: string, salt: Buffer): Promise<Buffer> {
  return new Promise((resolve, reject) => {
    scrypt(password, salt, PASSWORD_KEY_LENGTH, (error, key) => {
      if (error) reject(error);
      else resolve(key as Buffer);
    });
  });
}

export function getSessionSecret(): string {
  const secret = process.env.SESSION_SECRET;
  if (!secret || Buffer.byteLength(secret) < 32) {
    throw new Error("SESSION_SECRET must contain at least 32 bytes.");
  }
  return secret;
}

export function normalizeUserId(userId: string): string {
  return userId.normalize("NFKC").trim().toLowerCase();
}

export function isValidUserId(userId: string): boolean {
  return /^[a-z0-9][a-z0-9._-]{2,63}$/.test(userId);
}

export async function hashPassword(password: string): Promise<string> {
  const salt = randomBytes(16);
  const derivedKey = await deriveKey(password, salt);
  return `scrypt$${salt.toString("base64url")}$${derivedKey.toString("base64url")}`;
}

export async function verifyPassword(
  password: string,
  encodedHash: string | null | undefined,
): Promise<boolean> {
  if (!encodedHash) return false;
  const [algorithm, saltText, hashText, ...extra] = encodedHash.split("$");
  if (algorithm !== "scrypt" || !saltText || !hashText || extra.length > 0) {
    return false;
  }

  try {
    const salt = Buffer.from(saltText, "base64url");
    const expected = Buffer.from(hashText, "base64url");
    if (salt.length !== 16 || expected.length !== PASSWORD_KEY_LENGTH) return false;
    const actual = await deriveKey(password, salt);
    return timingSafeEqual(actual, expected);
  } catch {
    return false;
  }
}

export function createSessionToken(
  userId: number,
  secret = getSessionSecret(),
  now = Date.now(),
): string {
  const payload = Buffer.from(
    JSON.stringify({
      userId,
      expiresAt: Math.floor(now / 1000) + SESSION_LIFETIME_SECONDS,
    }),
  ).toString("base64url");
  const signature = createHmac("sha256", secret)
    .update(payload)
    .digest("base64url");
  return `${payload}.${signature}`;
}

export function verifySessionToken(
  token: string | undefined,
  secret = getSessionSecret(),
  now = Date.now(),
): number | null {
  if (!token) return null;
  const [payload, signature, ...extra] = token.split(".");
  if (!payload || !signature || extra.length > 0) return null;

  const expectedSignature = createHmac("sha256", secret)
    .update(payload)
    .digest();
  let suppliedSignature: Buffer;
  try {
    suppliedSignature = Buffer.from(signature, "base64url");
  } catch {
    return null;
  }
  if (
    suppliedSignature.length !== expectedSignature.length ||
    !timingSafeEqual(expectedSignature, suppliedSignature)
  ) {
    return null;
  }

  try {
    const decoded = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as {
      userId?: unknown;
      expiresAt?: unknown;
    };
    if (
      !Number.isSafeInteger(decoded.userId) ||
      (decoded.userId as number) <= 0 ||
      !Number.isSafeInteger(decoded.expiresAt) ||
      (decoded.expiresAt as number) <= Math.floor(now / 1000)
    ) {
      return null;
    }
    return decoded.userId as number;
  } catch {
    return null;
  }
}
