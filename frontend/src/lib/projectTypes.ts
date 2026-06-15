// Project type options — mirror backend Project.ProjectType. Keep in sync.
export const PROJECT_TYPES = [
  { value: "commercial", label: "Commercial" },
  { value: "residential", label: "Residential" },
  { value: "infrastructure", label: "Infrastructure" },
  { value: "industrial", label: "Industrial" },
] as const;

// Mirror backend Project.Priority.
export const PRIORITIES = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
] as const;
