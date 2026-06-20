import { colors, fontFamily, radius, space, typeScale } from "./tokens";

export interface StatCardProps {
  label: string;
  /** Pass null/undefined for "no data yet" — rendered as an em dash, never coerced to 0. */
  value: string | number | null | undefined;
  hint?: string;
}

export function StatCard({ label, value, hint }: StatCardProps) {
  const display = value === null || value === undefined ? "—" : value;
  return (
    <div
      style={{
        background: colors.surface,
        border: `1px solid ${colors.border}`,
        borderRadius: radius.md,
        padding: space.lg,
        minWidth: 160,
        fontFamily,
      }}
    >
      <div
        style={{
          color: colors.textMuted,
          fontSize: typeScale.sm,
          textTransform: "uppercase",
          letterSpacing: 0.4,
          marginBottom: space.xs,
        }}
      >
        {label}
      </div>
      <div style={{ color: colors.text, fontSize: typeScale.xl, fontWeight: 700 }}>{display}</div>
      {hint && (
        <div style={{ color: colors.textFaint, fontSize: typeScale.xs, marginTop: space.xs }}>
          {hint}
        </div>
      )}
    </div>
  );
}
