import type { CSSProperties } from "react";
import { colors, radius } from "./tokens";

export interface SkeletonProps {
  width?: number | string;
  height?: number | string;
  style?: CSSProperties;
}

/** A loading placeholder block that reserves the same space as the content
 * it stands in for, so swapping it out never causes layout shift. */
export function Skeleton({ width = "100%", height = 16, style }: SkeletonProps) {
  return (
    <div
      role="status"
      aria-label="Loading"
      style={{
        width,
        height,
        borderRadius: radius.sm,
        background: `linear-gradient(90deg, ${colors.surfaceRaised} 25%, ${colors.border} 50%, ${colors.surfaceRaised} 75%)`,
        backgroundSize: "200% 100%",
        animation: "agentforge-skeleton-shimmer 1.4s ease-in-out infinite",
        ...style,
      }}
    />
  );
}

// Injected once: vite/CSS-in-JS isn't set up in this project, and a single
// global @keyframes rule is the simplest way to animate the shimmer without
// adding a stylesheet dependency.
if (typeof document !== "undefined" && !document.getElementById("agentforge-skeleton-keyframes")) {
  const style = document.createElement("style");
  style.id = "agentforge-skeleton-keyframes";
  style.textContent = `@keyframes agentforge-skeleton-shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }`;
  document.head.appendChild(style);
}
