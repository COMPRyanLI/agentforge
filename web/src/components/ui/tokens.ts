// Design tokens for the run-history/timeline UI. Reuses the dark palette
// already used throughout App.tsx/RunPanel.tsx so these new pages don't
// visually clash with the existing builder.

export const colors = {
  bg: "#0b1020",
  surface: "#0f172a",
  surfaceRaised: "#1e293b",
  border: "#1e293b",
  borderStrong: "#334155",
  text: "#e2e8f0",
  textMuted: "#94a3b8",
  textFaint: "#64748b",
  accent: "#3b82f6",
  focusRing: "#60a5fa",
} as const;

// AA-contrast-checked against the dark surfaces above.
export const statusColors = {
  succeeded: { fg: "#4ade80", bg: "rgba(34, 197, 94, 0.15)" },
  failed: { fg: "#f87171", bg: "rgba(239, 68, 68, 0.15)" },
  interrupted: { fg: "#fbbf24", bg: "rgba(245, 158, 11, 0.15)" },
  running: { fg: "#60a5fa", bg: "rgba(59, 130, 246, 0.15)" },
  pending: { fg: "#94a3b8", bg: "rgba(148, 163, 184, 0.15)" },
} as const;

export type RunStatus = keyof typeof statusColors;

export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const typeScale = {
  xs: 11,
  sm: 12,
  base: 13,
  md: 14,
  lg: 18,
  xl: 28,
} as const;

export const radius = {
  sm: 4,
  md: 8,
  lg: 12,
} as const;

export const fontFamily = "system-ui, sans-serif";
export const monoFontFamily = "monospace";
