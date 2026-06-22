// Builds a "Tower A › Zone 2 › Block C" path by walking scope parent pointers.
// Used by the Schedule tab's filtered (flat) views, where rows lose their tree
// indentation and need the ancestor chain spelled out instead.
import type { Scope } from "@/types/project";

export function scopeById(scopes: Scope[]): Map<string, Scope> {
  return new Map(scopes.map((s) => [s.id, s]));
}

export function scopePath(scopeId: string | null | undefined, byId: Map<string, Scope>): string {
  const parts: string[] = [];
  let current = scopeId ? byId.get(scopeId) : undefined;
  while (current) {
    parts.unshift(current.name);
    current = current.parent ? byId.get(current.parent) : undefined;
  }
  return parts.join(" › ");
}
