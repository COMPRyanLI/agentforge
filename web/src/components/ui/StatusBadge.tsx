import { fontFamily, radius, space, statusColors, typeScale, type RunStatus } from "./tokens";

export interface StatusBadgeProps {
  status: string;
}

function isKnownStatus(status: string): status is RunStatus {
  return status in statusColors;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const palette = isKnownStatus(status) ? statusColors[status] : statusColors.pending;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: `${space.xs / 2}px ${space.sm}px`,
        borderRadius: radius.sm,
        fontFamily,
        fontSize: typeScale.xs,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: 0.4,
        color: palette.fg,
        background: palette.bg,
      }}
    >
      {status}
    </span>
  );
}
