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
import { History, Rocket, Save, User, Wrench } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type CSSProperties, type DragEvent } from "react";
import { BrowserRouter, Link, Route, Routes, useLocation } from "react-router-dom";
import { createAgent, createVersion, getCurrentVersion, publishAgent } from "./api/agents";
import { listTools, type ToolRead } from "./api/tools";
import { AuthProvider, useAuth } from "./auth/AuthContext";
import { ConfigPanel, type ConfigurableNode } from "./components/ConfigPanel";
import { NODE_DRAG_MIME, Palette } from "./components/Palette";
import { RunPanel } from "./components/RunPanel";
import { ToolBuilder } from "./components/ToolBuilder";
import { toGraphJson, type NodeType } from "./lib/graph";
import { graphJsonToReactFlow } from "./lib/graphToFlow";
import { validateGraph } from "./lib/validateGraph";
import { ConditionNode } from "./nodes/ConditionNode";
import { InputNode } from "./nodes/InputNode";
import { LLMNode } from "./nodes/LLMNode";
import { LoopNode } from "./nodes/LoopNode";
import { OutputNode } from "./nodes/OutputNode";
import { ToolNode } from "./nodes/ToolNode";
import { MarketplaceDetail } from "./pages/MarketplaceDetail";
import { MarketplaceList } from "./pages/MarketplaceList";
import { RunHistory } from "./pages/RunHistory";
import { RunTimeline } from "./pages/RunTimeline";
import { TemplateGallery } from "./pages/TemplateGallery";

export interface OpenAgentState {
  agentId: string;
  agentName: string;
}

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

function Canvas() {
  const { token } = useAuth();
  const location = useLocation();
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

  // Arriving from an install or template-clone: the new agent already has a
  // saved version — fetch and apply it so the canvas shows the real graph
  // instead of the default starter skeleton. loadedAgentIdRef avoids
  // refetching on every token keystroke while still allowing a retry (via
  // the catch resetting it) if the fetch fails.
  const loadedAgentIdRef = useRef<string | null>(null);
  useEffect(() => {
    const opened = location.state as OpenAgentState | null;
    if (!opened?.agentId || !token) return;
    if (loadedAgentIdRef.current === opened.agentId) return;
    loadedAgentIdRef.current = opened.agentId;
    setAgentId(opened.agentId);
    setAgentName(opened.agentName);
    getCurrentVersion(opened.agentId, token)
      .then((version) => {
        const { nodes: loadedNodes, edges: loadedEdges } = graphJsonToReactFlow(
          version.graph_json
        );
        setNodes(loadedNodes);
        setEdges(loadedEdges);
        setDirty(false);
      })
      .catch((err) => {
        loadedAgentIdRef.current = null;
        setSaveErrors([String(err)]);
      });
  }, [location.state, token, setNodes, setEdges]);

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

  const handlePublish = useCallback(async () => {
    try {
      await publishAgent(agentId, token);
      setSaveErrors([]);
    } catch (err) {
      setSaveErrors([String(err)]);
    }
  }, [agentId, token]);

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
    <div
      style={{
        width: "100%",
        height: "100%",
        background: "var(--af-bg-canvas)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Top bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 12px",
          borderBottom: "1px solid var(--af-border)",
          background: "var(--af-bg-surface)",
          color: "var(--af-text)",
          fontFamily: "var(--af-font-sans)",
          fontSize: 12,
        }}
      >
        <input
          placeholder="Untitled agent"
          value={agentName}
          onChange={(e) => setAgentName(e.target.value)}
          style={titleInputStyle}
          aria-label="Agent name"
        />
        <span style={{ color: "var(--af-text-faint)", fontSize: 11 }}>
          {agentId ? `${agentId.slice(0, 8)}…` : "Not created yet"}
        </span>

        <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: "auto" }}>
          {!agentId && (
            <button onClick={handleCreateAgent} style={secondaryButtonStyle} disabled={!token}>
              Create agent
            </button>
          )}
          <button onClick={handleSave} style={secondaryButtonStyle} disabled={!agentId}>
            <Save size={13} /> Save
          </button>
          <button onClick={() => setToolBuilderOpen(true)} style={secondaryButtonStyle} disabled={!token}>
            <Wrench size={13} /> Tool
          </button>
          {agentId ? (
            <Link to={`/agents/${agentId}/runs`} style={{ ...secondaryButtonStyle, textDecoration: "none" }}>
              <History size={13} /> Runs
            </Link>
          ) : (
            <span style={{ ...secondaryButtonStyle, opacity: 0.5, cursor: "not-allowed" }}>
              <History size={13} /> Runs
            </span>
          )}
          <button
            onClick={handlePublish}
            style={primaryButtonStyle}
            disabled={!agentId || dirty}
          >
            <Rocket size={13} /> Publish
          </button>
        </div>
      </div>
      {saveErrors.length > 0 && (
        <div
          style={{
            padding: "6px 12px",
            background: "var(--af-bg-surface)",
            borderBottom: "1px solid var(--af-border)",
            color: "#f87171",
            fontSize: 11,
          }}
        >
          {saveErrors.join(" | ")}
        </div>
      )}

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
            <Background color="var(--af-border)" />
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

const titleInputStyle: CSSProperties = {
  background: "transparent",
  border: "1px solid transparent",
  borderRadius: 4,
  padding: "4px 6px",
  color: "var(--af-text)",
  fontSize: 14,
  fontWeight: 600,
  fontFamily: "var(--af-font-sans)",
  minWidth: 160,
};

const topInputStyle: CSSProperties = {
  background: "var(--af-bg-surface-raised)",
  border: "1px solid var(--af-border)",
  borderRadius: 4,
  padding: "4px 8px",
  color: "var(--af-text)",
  fontSize: 12,
  fontFamily: "var(--af-font-sans)",
};

const secondaryButtonStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 5,
  background: "var(--af-bg-surface-raised)",
  border: "1px solid var(--af-border)",
  borderRadius: 4,
  padding: "5px 10px",
  color: "var(--af-text)",
  fontSize: 12,
  cursor: "pointer",
};

const primaryButtonStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 5,
  background: "var(--af-accent)",
  border: "none",
  borderRadius: 4,
  padding: "5px 12px",
  color: "var(--af-accent-fg)",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
};

function AccountMenu() {
  const { token, setToken } = useAuth();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as globalThis.Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  return (
    <div ref={containerRef} style={{ position: "relative", marginLeft: "auto" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Account menu"
        aria-expanded={open}
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 28,
          height: 28,
          borderRadius: "50%",
          border: "1px solid var(--af-border)",
          background: token ? "var(--af-accent)" : "var(--af-bg-surface-raised)",
          color: token ? "var(--af-accent-fg)" : "var(--af-text-muted)",
          cursor: "pointer",
        }}
      >
        <User size={14} />
      </button>
      {open && (
        <div
          style={{
            position: "absolute",
            right: 0,
            top: "calc(100% + 6px)",
            width: 240,
            padding: 12,
            borderRadius: "var(--af-radius-md)",
            border: "1px solid var(--af-border)",
            background: "var(--af-bg-surface-raised)",
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            zIndex: 50,
          }}
        >
          <div style={{ color: "var(--af-text-muted)", fontSize: 11, marginBottom: 6 }}>
            API token
          </div>
          <input
            type="password"
            placeholder="JWT token"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            style={{ ...topInputStyle, width: "100%", boxSizing: "border-box" }}
          />
        </div>
      )}
    </div>
  );
}

function NavBar() {
  const linkStyle: CSSProperties = { color: "var(--af-text)", textDecoration: "none", fontSize: 12 };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        padding: "8px 12px",
        borderBottom: "1px solid var(--af-border)",
        background: "var(--af-bg-canvas)",
        fontFamily: "var(--af-font-sans)",
      }}
    >
      <Link to="/" style={{ ...linkStyle, fontWeight: 700 }}>
        AgentForge
      </Link>
      <Link to="/" style={linkStyle}>
        Builder
      </Link>
      <Link to="/marketplace" style={linkStyle}>
        Marketplace
      </Link>
      <Link to="/templates" style={linkStyle}>
        Templates
      </Link>
      <AccountMenu />
    </div>
  );
}

function BuilderPage() {
  return (
    <ReactFlowProvider>
      <Canvas />
    </ReactFlowProvider>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <div style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
          <NavBar />
          <div style={{ flex: 1, overflow: "hidden" }}>
            <Routes>
              <Route path="/" element={<BuilderPage />} />
              <Route path="/marketplace" element={<MarketplaceList />} />
              <Route path="/marketplace/:agentId" element={<MarketplaceDetail />} />
              <Route path="/templates" element={<TemplateGallery />} />
              <Route path="/agents/:agentId/runs" element={<RunHistory />} />
              <Route path="/runs/:runId/timeline" element={<RunTimeline />} />
            </Routes>
          </div>
        </div>
      </BrowserRouter>
    </AuthProvider>
  );
}
