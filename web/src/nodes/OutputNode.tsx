import { LogOut } from "lucide-react";
import { NodeShell } from "./NodeShell";

export function OutputNode() {
  return (
    <NodeShell
      icon={LogOut}
      accent="var(--af-node-output)"
      label="Output"
      subtitle="Run exit point"
      sourceHandles="none"
    />
  );
}
