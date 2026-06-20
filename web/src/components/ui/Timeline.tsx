import { useState } from "react";
import { colors, fontFamily, monoFontFamily, radius, space, typeScale } from "./tokens";

export interface TimelineItem {
  id: string;
  /** Hex color for this item's marker dot and accent. */
  color: string;
  icon: string;
  title: string;
  nodeId: string;
  timestamp: string;
  /** Small inline badges (e.g. token counts, latency) rendered next to the title. */
  badges?: { label: string; value: string }[];
  payload: Record<string, unknown>;
}

export interface TimelineProps {
  items: TimelineItem[];
}

function PayloadDisclosure({ payload, itemId }: { payload: Record<string, unknown>; itemId: string }) {
  const [open, setOpen] = useState(false);
  const hasContent = Object.keys(payload).length > 0;
  if (!hasContent) return null;
  const panelId = `agentforge-timeline-payload-${itemId}`;
  return (
    <div style={{ marginTop: space.xs }}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={panelId}
        style={{
          background: "none",
          border: "none",
          color: colors.textMuted,
          cursor: "pointer",
          fontSize: typeScale.xs,
          padding: 0,
        }}
      >
        {open ? "▾ Hide payload" : "▸ Show payload"}
      </button>
      {open && (
        <pre
          id={panelId}
          style={{
            marginTop: space.xs,
            padding: space.sm,
            background: colors.bg,
            border: `1px solid ${colors.border}`,
            borderRadius: radius.sm,
            color: colors.textMuted,
            fontFamily: monoFontFamily,
            fontSize: typeScale.xs,
            overflowX: "auto",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {JSON.stringify(payload, null, 2)}
        </pre>
      )}
    </div>
  );
}

/** A vertical connector-spine timeline: each item gets a colored marker on
 * the spine plus a content block. Used to render a run's event history. */
export function Timeline({ items }: TimelineProps) {
  if (items.length === 0) return null;
  return (
    <ol style={{ listStyle: "none", margin: 0, padding: 0, fontFamily }}>
      {items.map((item, i) => (
        <li key={item.id} style={{ position: "relative", paddingLeft: space.xl, paddingBottom: space.lg }}>
          {i < items.length - 1 && (
            <span
              aria-hidden="true"
              style={{
                position: "absolute",
                left: 5,
                top: 14,
                bottom: 0,
                width: 2,
                background: colors.border,
              }}
            />
          )}
          <span
            aria-hidden="true"
            style={{
              position: "absolute",
              left: 0,
              top: 2,
              width: 12,
              height: 12,
              borderRadius: "50%",
              background: item.color,
            }}
          />
          <div style={{ display: "flex", alignItems: "baseline", gap: space.sm, flexWrap: "wrap" }}>
            <span style={{ color: colors.text, fontWeight: 700, fontSize: typeScale.base }}>
              {item.icon} {item.title}
            </span>
            <span style={{ color: colors.textFaint, fontSize: typeScale.xs }}>{item.nodeId}</span>
            <time
              dateTime={item.timestamp}
              title={new Date(item.timestamp).toLocaleString()}
              style={{ color: colors.textFaint, fontSize: typeScale.xs }}
            >
              {new Date(item.timestamp).toLocaleTimeString()}
            </time>
          </div>
          {item.badges && item.badges.length > 0 && (
            <div style={{ display: "flex", gap: space.xs, marginTop: space.xs, flexWrap: "wrap" }}>
              {item.badges.map((b) => (
                <span
                  key={b.label}
                  style={{
                    background: colors.surfaceRaised,
                    color: colors.textMuted,
                    borderRadius: radius.sm,
                    padding: `1px ${space.xs}px`,
                    fontSize: typeScale.xs,
                  }}
                >
                  {b.label}: {b.value}
                </span>
              ))}
            </div>
          )}
          <PayloadDisclosure payload={item.payload} itemId={item.id} />
        </li>
      ))}
    </ol>
  );
}
