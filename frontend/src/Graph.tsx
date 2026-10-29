import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  useNodesInitialized,
  useReactFlow,
  useNodesState,
} from '@xyflow/react';
import type { NodeChange, NodeProps, XYPosition } from '@xyflow/react';
import { executionGraph } from './executionGraph';
import type { ExecutionNode } from './executionGraph';
import type { Trace } from './types';
import '@xyflow/react/dist/style.css';

type Positions = Record<string, XYPosition>;
const layoutKey = (runId: string) => `alpha-mas:graph-layout:v1:${runId}`;

function readLayout(runId: string): Positions {
  try {
    const raw = localStorage.getItem(layoutKey(runId));
    if (!raw || raw.length > 100000) return {};
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    return Object.fromEntries(
      Object.entries(value).filter(
        ([, point]) =>
          point &&
          typeof point === 'object' &&
          typeof point.x === 'number' &&
          typeof point.y === 'number' &&
          Number.isFinite(point.x) &&
          Number.isFinite(point.y) &&
          Math.abs(point.x) < 1000000 &&
          Math.abs(point.y) < 1000000,
      ),
    );
  } catch {
    return {};
  }
}

function ExecutionComponent({ data }: NodeProps<ExecutionNode>) {
  return (
    <>
      <Handle id="in" type="target" position={Position.Left} />
      <Handle id="out" type="source" position={Position.Right} />
      <Handle id="feedback-in" type="target" position={Position.Top} style={{ left: '35%' }} />
      <Handle id="feedback-out" type="source" position={Position.Top} style={{ left: '65%' }} />
      <div>
        <small>{data.kind === 'tool' ? 'RESEARCH TOOL' : data.state.toUpperCase()}</small>
        <strong>{data.title}</strong>
        <span>
          {data.kind === 'tool'
            ? `${data.artifacts} computed artifacts`
            : `${data.provider} / ${data.model}`}
        </span>
      </div>
    </>
  );
}
const nodeTypes = { execution: ExecutionComponent };

interface GraphProps {
  runId: string;
  events: Trace[];
  onSelect: (id: string) => void;
}
export function Graph(props: GraphProps) {
  // New runs get independent state. Replays and tab switches reload this run's browser layout.
  return <InteractiveGraph key={props.runId} {...props} />;
}

function InteractiveGraph({ runId, events, onSelect }: GraphProps) {
  const projection = useMemo(() => executionGraph(events), [events]);
  const [initialPositions] = useState(() => readLayout(runId));
  const positions = useRef<Positions>(initialPositions);
  const manual = useRef(Object.keys(positions.current).length > 0);
  const [nodes, setNodes, applyChanges] = useNodesState<ExecutionNode>([]);
  const [hasLayout, setHasLayout] = useState(Object.keys(positions.current).length > 0);
  const [storageAvailable, setStorageAvailable] = useState(true);
  const [showTools, setShowTools] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const [expanded, setExpanded] = useState(false);
  const [focus, setFocus] = useState<string | null>(null);
  const [fitVersion, setFitVersion] = useState(0);

  const persist = useCallback(() => {
    const hasPositions = Object.keys(positions.current).length > 0;
    setHasLayout(hasPositions);
    try {
      if (hasPositions) localStorage.setItem(layoutKey(runId), JSON.stringify(positions.current));
      else localStorage.removeItem(layoutKey(runId));
      setStorageAvailable(true);
    } catch {
      setStorageAvailable(false);
    }
  }, [runId]);

  useEffect(() => {
    setNodes((previous) =>
      projection.nodes.map((node) => {
        const old = previous.find((item) => item.id === node.id);
        return {
          ...node,
          position: positions.current[node.id] ?? node.position,
          measured: old?.measured,
          selected: old?.selected,
          dragging: old?.dragging,
        };
      }),
    );
  }, [projection, setNodes]);

  const onNodesChange = useCallback(
    (changes: NodeChange<ExecutionNode>[]) => {
      for (const change of changes) {
        if (change.type === 'position' && change.position) {
          positions.current[change.id] = change.position;
          manual.current = true;
        }
      }
      applyChanges(changes);
      if (changes.some((c) => c.type === 'position' && c.position && c.dragging !== true))
        persist();
    },
    [applyChanges, persist],
  );

  const visible = nodes.filter((node) => showTools || node.data.kind === 'agent');
  const ids = new Set(visible.map((node) => node.id));
  const focused = focus && ids.has(focus) ? focus : null;
  const edges = projection.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
  const neighbors = new Set([focused]);
  for (const edge of edges) {
    if (edge.source === focused || edge.target === focused) {
      neighbors.add(edge.source);
      neighbors.add(edge.target);
    }
  }
  const displayNodes = visible.map((node) => ({
    ...node,
    style: { opacity: !focused || neighbors.has(node.id) ? 1 : 0.25 },
  }));
  const displayEdges = edges.map((edge) => ({
    ...edge,
    label:
      showLabels && edge.data?.kind !== 'tool'
        ? `${edge.data?.title}${(edge.data?.count ?? 0) > 1 ? ` · ${edge.data?.count}` : ''}`
        : undefined,
    style: {
      ...edge.style,
      opacity: !focused || edge.source === focused || edge.target === focused ? 1 : 0.12,
      strokeWidth: focused && (edge.source === focused || edge.target === focused) ? 2 : 1.25,
    },
  }));

  function arrange() {
    positions.current = {};
    manual.current = false;
    persist();
    setNodes(projection.nodes);
    setFitVersion((v) => v + 1);
  }

  return (
    <div className="graph-workspace">
      <div className="graph-toolbar" role="toolbar" aria-label="Execution graph controls">
        <div className="graph-actions">
          <button onClick={arrange} title="Reset saved positions to the default layout">
            Auto arrange
          </button>
          <button onClick={() => setFitVersion((v) => v + 1)}>Fit graph</button>
          <button
            aria-pressed={expanded}
            onClick={() => {
              setExpanded(!expanded);
              setFitVersion((v) => v + 1);
            }}
          >
            {expanded ? 'Collapse graph' : 'Expand graph'}
          </button>
        </div>
        <div className="graph-options">
          <label>
            <input
              type="checkbox"
              checked={showTools}
              onChange={(e) => {
                setShowTools(e.target.checked);
                setFocus(null);
                setFitVersion((v) => v + 1);
              }}
            />
            Show tools
          </label>
          <label>
            <input
              type="checkbox"
              checked={showLabels}
              onChange={(e) => setShowLabels(e.target.checked)}
            />
            Edge labels
          </label>
          {focused && <button onClick={() => setFocus(null)}>Clear highlight</button>}
        </div>
      </div>
      <div className={`graph${expanded ? ' graph-expanded' : ''}`}>
        <ReactFlow
          nodes={displayNodes}
          edges={displayEdges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onNodeDragStart={() => {
            manual.current = true;
          }}
          onNodeDragStop={persist}
          onMoveStart={(event) => {
            if (event) manual.current = true;
          }}
          onNodeClick={(_, node) => {
            setFocus(node.id);
            if (node.data.kind === 'agent') onSelect(node.id);
          }}
          onPaneClick={() => setFocus(null)}
          nodesDraggable
          nodesConnectable={false}
          edgesReconnectable={false}
          deleteKeyCode={null}
          minZoom={0.15}
          maxZoom={2}
          fitViewOptions={{ padding: 0.2, maxZoom: 1 }}
          proOptions={{ hideAttribution: true }}
        >
          <FitGraph
            topology={visible.map((n) => n.id).join('|')}
            version={fitVersion}
            manual={manual}
          />
          <Background color="#294039" gap={22} />
          <Controls
            showInteractive={false}
            onZoomIn={() => {
              manual.current = true;
            }}
            onZoomOut={() => {
              manual.current = true;
            }}
          />
          <MiniMap
            style={{ width: 140, height: 90 }}
            pannable
            zoomable
            nodeColor={(node) => (node.data.kind === 'tool' ? '#7c947d' : '#73be9c')}
            maskColor="#08120dc9"
          />
        </ReactFlow>
      </div>
      <div className="graph-hint">
        <span>
          Drag nodes to arrange · drag canvas to pan · click a node to highlight its links
        </span>
        <span aria-live="polite">
          {!storageAvailable
            ? 'Layout kept for this view'
            : hasLayout
              ? 'Layout saved for this run in this browser'
              : 'Solid: handoffs · dashed: tool calls'}
        </span>
      </div>
    </div>
  );
}

function FitGraph({
  topology,
  version,
  manual,
}: {
  topology: string;
  version: number;
  manual: { current: boolean };
}) {
  const initialized = useNodesInitialized();
  const { fitView } = useReactFlow();
  const fitted = useRef(false);
  const lastVersion = useRef(version);
  useEffect(() => {
    if (!initialized || !topology) return;
    if (!fitted.current || !manual.current || version !== lastVersion.current) {
      void fitView({ padding: 0.2, maxZoom: 1, duration: 0 });
      fitted.current = true;
    }
    lastVersion.current = version;
  }, [initialized, topology, version, manual, fitView]);
  return null;
}
