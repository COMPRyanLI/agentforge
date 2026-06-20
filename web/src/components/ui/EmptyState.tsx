import type { ReactNode } from "react";
import { colors, fontFamily, space, typeScale } from "./tokens";

export interface EmptyStateProps {
  message: string;
  action?: ReactNode;
}

export function EmptyState({ message, action }: EmptyStateProps) {
  return (
    <div
      style={{
        padding: space.xxl,
        textAlign: "center",
        color: colors.textMuted,
        fontFamily,
        fontSize: typeScale.base,
      }}
    >
      <div style={{ marginBottom: action ? space.md : 0 }}>{message}</div>
      {action}
    </div>
  );
}
