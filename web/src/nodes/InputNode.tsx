import { LogIn } from "lucide-react";
import { NodeShell } from "./NodeShell";

export function InputNode() {
  return (
    <NodeShell
      icon={LogIn}
      accent="var(--af-node-input)"
      label="Input"
      subtitle="Run entry point"
      showTarget={false}
    />
  );
}
