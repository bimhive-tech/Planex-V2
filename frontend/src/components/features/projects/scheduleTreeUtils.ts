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
