export const restrictedBettorExportRoles = [
  "admin",
  "compliance_reviewer",
  "restricted_analyst",
] as const;

export type WorkspaceRole =
  | "admin"
  | "analyst"
  | "compliance_reviewer"
  | "restricted_analyst"
  | "read_only";

export function isWorkspaceRole(value: unknown): value is WorkspaceRole {
  return (
    value === "admin" ||
    value === "analyst" ||
    value === "compliance_reviewer" ||
    value === "restricted_analyst" ||
    value === "read_only"
  );
}

export function hasActiveRole(
  role: unknown,
  status: unknown,
  permittedRoles: readonly string[],
): role is WorkspaceRole {
  return (
    status === "active" &&
    isWorkspaceRole(role) &&
    permittedRoles.includes(role)
  );
}

export function canExportRestrictedBettors(
  role: unknown,
  status: unknown = "active",
): boolean {
  return hasActiveRole(role, status, restrictedBettorExportRoles);
}
