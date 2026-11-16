import assert from "node:assert/strict";
import test from "node:test";
import {
  createSessionToken,
  hashPassword,
  verifyPassword,
  verifySessionToken,
} from "./local-auth-crypto";

test("local password hashes are salted and can be verified", async () => {
  const password = "correct horse battery staple";
  const firstHash = await hashPassword(password);
  const secondHash = await hashPassword(password);

  assert.notEqual(firstHash, secondHash);
  assert.equal(await verifyPassword(password, firstHash), true);
  assert.equal(await verifyPassword("wrong password", firstHash), false);
  assert.equal(await verifyPassword(password, null), false);
});

test("local sessions reject tampering, wrong keys, and expired cookies", () => {
  const secret = "test-signing-secret-with-at-least-32-bytes";
  const now = 1_800_000_000_000;
  const token = createSessionToken(42, secret, now);

  assert.equal(verifySessionToken(token, secret, now), 42);
  assert.equal(verifySessionToken(token, "another-test-secret-with-32-bytes", now), null);
  assert.equal(verifySessionToken(`${token}x`, secret, now), null);
  assert.equal(verifySessionToken(token, secret, now + 13 * 60 * 60 * 1000), null);
  assert.equal(verifySessionToken(undefined, secret, now), null);
});
