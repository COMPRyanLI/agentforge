import {
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { createAgent, createVersion } from "./api/agents";
import { listTools, type ToolRead } from "./api/tools";
import { ConfigPanel, type ConfigurableNode } from "./components/ConfigPanel";
import { NODE_DRAG_MIME, Palette } from "./components/Palette";
import { RunPanel } from "./components/RunPanel";
import { ToolBuilder } from "./components/ToolBuilder";
import type { GraphJson, NodeType } from "./lib/graph";
import { validateGraph } from "./lib/validateGraph";
import { ConditionNode } from "./nodes/ConditionNode";
import { InputNode } from "./nodes/InputNode";
import { LLMNode } from "./nodes/LLMNode";
import { LoopNode } from "./nodes/LoopNode";
import { OutputNode } from "./nodes/OutputNode";
import { ToolNode } from "./nodes/ToolNode";

const nodeTypes: NodeTypes = {
  input: InputNode,
  llm: LLMNode,
  tool: ToolNode,
  condition: ConditionNode,
  loop: LoopNode,
  output: OutputNode,
};

const DEFAULT_DATA: Record<NodeType, Record<string, unknown>> = {
  input: {},
  llm: { system_prompt: "You are a helpful assistant.", tools: [] },
  tool: { tool_id: "", require_approval: false },
  condition: { expr: "" },
  loop: { expr: "step_index >= 0", max_iterations: 3 },
  output: {},
};

const initialNodes: Node[] = [
  { id: "in", type: "input", position: { x: 60, y: 180 }, data: {} },
  { id: "llm1", type: "llm", position: { x: 280, y: 180 }, data: { ...DEFAULT_DATA.llm } },
  { id: "out", type: "output", position: { x: 540, y: 180 }, data: {} },
];

function toGraphJson(nodes: Node[], edges: Edge[]): GraphJson {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      type: n.type as NodeType,
      data: n.data as Record<string, unknown>,
    })),
    edges: edges.map((e) => ({
      source: e.source,
      target: e.target,
      ...(e.sourceHandle === "true" || e.sourceHandle === "false"
        ? { condition: e.sourceHandle }
        : {}),
    })),
  };
}

function Canvas() {
  const [token, setToken] = useState("");
  const [agentName, setAgentName] = useState("My Agent");
  const [agentId, setAgentId] = useState("");
  const [tools, setTools] = useState<ToolRead[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [dirty, setDirty] = useState(true);
  const [saveErrors, setSaveErrors] = useState<string[]>([]);
  const [toolBuilderOpen, setToolBuilderOpen] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([
    { id: "e1", source: "in", target: "llm1" },
    { id: "e2", source: "llm1", target: "out" },
  ]);
  const { screenToFlowPosition } = useReactFlow();
  const idCounter = useRef(0);

  const markDirty = useCallback(() => setDirty(true), []);

  useEffect(() => {
    if (!token) return;
    listTools(token)
      .then(setTools)
      .catch(() => setTools([]));
  }, [token]);

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      const type = event.dataTransfer.getData(NODE_DRAG_MIME) as NodeType;
      if (!type) return;
      const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const id = `${type}-${idCounter.current++}`;
      setNodes((nds) => nds.concat({ id, type, position, data: { ...DEFAULT_DATA[type] } }));
      markDirty();
    },
    [screenToFlowPosition, setNodes, markDirty]
  );

  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) => addEdge(connection, eds));
      markDirty();
    },
    [setEdges, markDirty]
  );

  const handleNodesChange = useCallback(
    (changes: Parameters<typeof onNodesChange>[0]) => {
      onNodesChange(changes);
      markDirty();
    },
    [onNodesChange, markDirty]
  );

  const handleEdgesChange = useCallback(
    (changes: Parameters<typeof onEdgesChange>[0]) => {
      onEdgesChange(changes);
      markDirty();
    },
    [onEdgesChange, markDirty]
  );

  const handleConfigChange = useCallback(
    (nodeId: string, data: Record<string, unknown>) => {
      setNodes((nds) => nds.map((n) => (n.id === nodeId ? { ...n, data } : n)));
      markDirty();
    },
    [setNodes, markDirty]
  );

  const handleCreateAgent = useCallback(async () => {
    try {
      const agent = await createAgent(agentName || "Untitled Agent", token);
      setAgentId(agent.id);
      setSaveErrors([]);
    } catch (err) {
      setSaveErrors([String(err)]);
    }
  }, [agentName, token]);

  const handleSave = useCallback(async () => {
    const graph = toGraphJson(nodes, edges);
    const errors = validateGraph(graph);
    if (errors.length > 0) {
      setSaveErrors(errors);
      return;
    }
    if (!agentId) {
      setSaveErrors(["Create an agent first."]);
      return;
    }
    try {
      await createVersion(agentId, graph, token);
      setSaveErrors([]);
      setDirty(false);
    } catch (err) {
      setSaveErrors([String(err)]);
    }
  }, [nodes, edges, agentId, token]);

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);
  const configurableNode: ConfigurableNode | null = selectedNode
    ? {
        id: selectedNode.id,
        type: selectedNode.type ?? "",
        data: selectedNode.data as Record<string, unknown>,
      }
    : null;

  const disabledReason = !agentId
    ? "Create an agent first."
    : dirty
      ? "Save the graph before testing."
      : null;

  return (
    <div style={{ width: "100vw", height: "100vh", background: "#0b1020", display: "flex", flexDirection: "column" }}>
      {/* Top bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 12px",
          borderBottom: "1px solid #1e293b",
          background: "#0f172a",
          color: "#e2e8f0",
          fontFamily: "system-ui, sans-serif",
          fontSize: 12,
        }}
      >
        <input
          type="password"
          placeholder="JWT token"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          style={topInputStyle}
        />
        <input
          placeholder="Agent name"
          value={agentName}
          onChange={(e) => setAgentName(e.target.value)}
          style={topInputStyle}
        />
        <button onClick={handleCreateAgent} style={topButtonStyle} disabled={!token}>
          Create Agent
        </button>
        <div style={{ color: "#64748b" }}>
          {agentId ? `agent: ${agentId.slice(0, 8)}…` : "(no agent yet)"}
        </div>
        <button onClick={handleSave} style={topButtonStyle} disabled={!agentId}>
          Save Graph
        </button>
        <button onClick={() => setToolBuilderOpen(true)} style={topButtonStyle} disabled={!token}>
          + HTTP Tool
        </button>
        {saveErrors.length > 0 && (
          <div style={{ color: "#ef4444", fontSize: 11 }}>{saveErrors.join(" | ")}</div>
        )}
      </div>

      {/* Body */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        <Palette />
        <div style={{ flex: 1, position: "relative" }} onDrop={onDrop} onDragOver={onDragOver}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={handleNodesChange}
            onEdgesChange={handleEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
            onPaneClick={() => setSelectedNodeId(null)}
            fitView
          >
            <Background />
            <Controls />
          </ReactFlow>
        </div>
        <ConfigPanel node={configurableNode} tools={tools} onChange={handleConfigChange} />
        <RunPanel token={token} agentId={agentId} disabledReason={disabledReason} />
      </div>

      {toolBuilderOpen && (
        <ToolBuilder
          token={token}
          onCreated={(tool) => setTools((prev) => [...prev, tool])}
          onClose={() => setToolBuilderOpen(false)}
        />
      )}
    </div>
  );
}

const topInputStyle = {
  background: "#1e293b",
  border: "1px solid #334155",
  borderRadius: 4,
  padding: "4px 8px",
  color: "#e2e8f0",
  fontSize: 12,
};

const topButtonStyle = {
  background: "#3b82f6",
  border: "none",
  borderRadius: 4,
  padding: "5px 10px",
  color: "#fff",
  fontSize: 12,
  cursor: "pointer",
};

export default function App() {
  return (
    <ReactFlowProvider>
      <Canvas />
    </ReactFlowProvider>
  );
}
