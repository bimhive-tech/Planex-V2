// Breakpoint px constants for JS use. MUST mirror the @media values in CSS
// (CSS custom properties can't be used inside @media conditions).
export const BREAKPOINTS = {
  tablet: 768,
  desktop: 1024,
} as const;

export type BreakpointName = keyof typeof BREAKPOINTS;
