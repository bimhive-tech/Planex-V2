// Which of a project's own levels play the "zone / subzone / work package"
// roles the Schedule tab filters by.
//
// Mirrors apps/reports/services.py's `_scope_roles` and models.py's
// PLACE_SCOPE_TYPES / WORK_SCOPE_TYPES — keep the three in step. Naming the
// roles by literal scope type only fits a tree shaped stage > zone > area; a
// Planex-coded P6 file nests whichever of the legend's twelve slots it uses,
// so Cairo Airport arrives as part > level > discipline > sub-discipline and
// every "zone" filter came up empty.
import type { Scope, ScopeType } from "@/types/project";

/** Levels that say WHERE the work is. */
export const PLACE_SCOPE_TYPES: readonly ScopeType[] = [
  "area", "sub_area", "stage", "zone", "part", "unit", "level", "building",
];

/** Levels that say WHAT the work is — what activities hang off. */
export const WORK_SCOPE_TYPES: readonly ScopeType[] = [
  "discipline", "sub_discipline", "phase", "task",
];

export interface ScopeRoles {
  /** The level progress is reported per. */
  zone: ScopeType | null;
  /** The level below it, charted inside each zone. */
  subzone: ScopeType | null;
}

/**
 * Read the roles off the tree. A zone is the reporting unit wherever a project
 * has one, so a tree that names its zones keeps the roles it always had —
 * including the zone-tracker shape, where zone is the ROOT and reading purely
 * by depth would demote it. Only a tree with no zone falls back to position,
 * and there the deepest place is the unit: it is what activities sit under.
 */
export function scopeRoles(childrenOf: Map<string | null, Scope[]>): ScopeRoles {
  const shallowest = new Map<ScopeType, number>();
  const walk = (parent: string | null, depth: number) => {
    for (const s of childrenOf.get(parent) ?? []) {
      if (PLACE_SCOPE_TYPES.includes(s.scope_type)) {
        const seen = shallowest.get(s.scope_type);
        if (seen === undefined || depth < seen) shallowest.set(s.scope_type, depth);
      }
      walk(s.id, depth + 1);
    }
  };
  walk(null, 0);
  if (shallowest.size === 0) return { zone: null, subzone: null };

  const order = [...shallowest.entries()].sort((a, b) => a[1] - b[1] || a[0].localeCompare(b[0]));
  const zone = shallowest.has("zone") ? "zone" : order[order.length - 1][0];
  const zoneDepth = shallowest.get(zone)!;
  const below = order.filter(([, d]) => d > zoneDepth).map(([t]) => t);
  // "area" keeps its role wherever it exists, so a tree with both a building
  // and an area level doesn't quietly swap which one the filter offers.
  const subzone = below.includes("area") ? "area" : (below[0] ?? null);
  return { zone, subzone };
}
