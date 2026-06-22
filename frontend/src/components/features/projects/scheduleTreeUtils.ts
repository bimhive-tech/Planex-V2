// Builds parent->children lookups and progress/activity-count maps from the
// flat scope list returned by the structure endpoint.
import type { ProjectStructure, Scope } from "@/types/project";

export function buildTree(data: ProjectStructure | null) {
  const childrenOf = new Map<string | null, Scope[]>();
  if (data) {
    for (const s of data.scopes) {
      const key = s.parent;
      if (!childrenOf.has(key)) childrenOf.set(key, []);
      childrenOf.get(key)!.push(s);
    }
  }
  const progress = data?.scope_progress ?? {};
  const progressOf = (scopeId: string): number => progress[scopeId] ?? 0;
  const activityCountOf = data?.scope_activity_counts ?? {};
  return { childrenOf, progressOf, activityCountOf };
}

function collectDescendants(id: string, childrenOf: Map<string | null, Scope[]>, into: Set<string>) {
  into.add(id);
  for (const c of childrenOf.get(id) ?? []) collectDescendants(c.id, childrenOf, into);
}

export interface ResolvedScheduleFilter {
  // null = no filter active (show everything); otherwise the exact set of
  // scope ids the tree should render.
  visibleIds: Set<string> | null;
  subzoneScope: Scope | null;
  phaseScope: Scope | null;
}

// Walks Zone -> Subzone -> Phase by name (subzone/phase names repeat across
// zones in imported zone trackers, so they're matched by name, not id; Zone
// is matched by id since it's the one truly unique root). Stops at the
// deepest level it can resolve and reveals everything below that point.
export function resolveScheduleFilter(
  childrenOf: Map<string | null, Scope[]>,
  zoneId: string,
  subzoneName: string,
  phaseName: string,
): ResolvedScheduleFilter {
  if (!zoneId) return { visibleIds: null, subzoneScope: null, phaseScope: null };

  const ids = new Set<string>([zoneId]);
  let containerId = zoneId;
  let subzoneScope: Scope | null = null;
  let phaseScope: Scope | null = null;

  if (subzoneName) {
    subzoneScope = (childrenOf.get(zoneId) ?? []).find((c) => c.name === subzoneName) ?? null;
    if (subzoneScope) {
      ids.add(subzoneScope.id);
      containerId = subzoneScope.id;

      if (phaseName) {
        phaseScope = (childrenOf.get(subzoneScope.id) ?? []).find((c) => c.name === phaseName) ?? null;
        if (phaseScope) {
          ids.add(phaseScope.id);
          containerId = phaseScope.id;
        }
      }
    }
  }

  collectDescendants(containerId, childrenOf, ids);
  return { visibleIds: ids, subzoneScope, phaseScope };
}
