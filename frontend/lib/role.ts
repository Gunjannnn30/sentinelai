// Client-side role gating. The server remains the source of truth (every
// endpoint enforces roles too); this only hides or disables UI the current
// role cannot use.
import type { Role } from "./types";

export const ROLE_ORDER: Role[] = ["viewer", "developer", "admin", "owner"];

export function roleAtLeast(role: Role | undefined | null, min: Role): boolean {
  if (!role) return false;
  return ROLE_ORDER.indexOf(role) >= ROLE_ORDER.indexOf(min);
}

/** Mutations (POST/PUT/PATCH/DELETE) generally need developer or more. */
export const canWrite = (role: Role | undefined | null) => roleAtLeast(role, "developer");
/** Admin-only settings: members, teams, providers, models, settings, projects. */
export const canAdmin = (role: Role | undefined | null) => roleAtLeast(role, "admin");
/** Policy evaluation needs developer or more. */
export const canEvaluate = (role: Role | undefined | null) => roleAtLeast(role, "developer");
