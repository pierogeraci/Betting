import type { NextFunction, Request, Response } from "express";
/**
 * Access is intentionally open for this no-login prototype.
 * Do not use this configuration for sensitive or production datasets.
 */

// Compatibility middleware only: the prototype has no authentication or role enforcement.
export function requireRole(..._roles: string[]) {
  return (_req: Request, _res: Response, next: NextFunction): void => next();
}
