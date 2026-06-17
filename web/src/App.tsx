import {
  Background,
  Controls,
  ReactFlow,
  type Edge,
  type Node,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { LLMNode } from "./nodes/LLMNode";
import { RunPanel } from "./components/RunPanel";

const nodeTypes: NodeTypes = { llm: LLMNode };

const initialNodes: Node[] = [
  { id: "1", type: "llm", position: { x: 200, y: 150 }, data: { label: "Gemma LLM" } },
];
const initialEdges: Edge[] = [];

export default function App() {
  return (
    <div style={{ width: "100vw", height: "100vh", background: "#0b1020" }}>
      {/* Canvas takes full viewport minus the run panel width */}
      <div style={{ position: "absolute", inset: 0, right: 380 }}>
        <ReactFlow
          nodes={initialNodes}
          edges={initialEdges}
          nodeTypes={nodeTypes}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
      <RunPanel />
    </div>
  );
}
