import { useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  Position,
  useNodesInitialized,
  useReactFlow,
} from '@xyflow/react';
import type { Node, Edge } from '@xyflow/react';
import type { Trace } from './types';
import '@xyflow/react/dist/style.css';

export function Graph({ events, onSelect }: { events: Trace[]; onSelect: (id: string) => void }) {
  const starts = events.filter((e) => e.event_type === 'agent.started');
  const nodes: Node[] = starts.map((start, index) => {
    const own = events.filter((e) => e.agent_id === start.agent_id);
    const last = own.at(-1)!;
    const done = own.some((e) => e.event_type === 'agent.completed');
    const terminal = events.at(-1)?.event_type;
    const state = done
      ? 'completed'
      : terminal === 'run.cancelled'
        ? 'cancelled'
        : terminal?.startsWith('run.') && terminal !== 'run.started'
          ? 'failed'
          : last.status === 'running'
            ? 'running'
            : 'waiting';
    const model = own.findLast((e) => e.model_id);
    return {
      id: start.agent_id!,
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      position: { x: index === 0 ? 30 : 310, y: index === 0 ? 110 : (index - 1) * 145 + 20 },
      data: {
        label: (
          <div>
            <small>{state.toUpperCase()}</small>
            <strong>{start.agent_id?.replaceAll('_', ' ')}</strong>
            <span>
              {model?.provider_id ?? 'pending'} / {model?.model_id ?? 'unassigned'}
            </span>
          </div>
        ),
      },
      className: `agent-node ${state}`,
    };
  });
  const pairs = new Map<string, Edge>();
  events
    .filter((e) => e.event_type.startsWith('handoff.') || e.event_type === 'revision.requested')
    .forEach((e) => {
      const target =
        e.event_type === 'revision.requested' ? 'generator' : String(e.metadata.recipient ?? '');
      if (!e.agent_id || !target || !nodes.some((n) => n.id === target)) return;
      const source = e.event_type === 'revision.requested' ? 'verifier' : e.agent_id;
      const key = `${source}-${target}`;
      pairs.set(key, {
        id: key,
        source,
        target,
        label: e.event_type.replace('handoff.', ''),
        animated: e.status === 'running',
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: '#45b6a0' },
      });
    });
  const tools = [
    ...new Set(
      events.filter((e) => e.event_type === 'tool.started').map((e) => String(e.metadata.tool)),
    ),
  ];
  tools.forEach((tool, index) => {
    const finished = events.filter(
      (e) => e.event_type === 'tool.completed' && e.metadata.tool === tool,
    );
    nodes.push({
      id: `tool:${tool}`,
      targetPosition: Position.Left,
      position: { x: 620, y: index * 115 + 20 },
      data: {
        label: (
          <div>
            <small>RESEARCH TOOL</small>
            <strong>{tool.replaceAll('_', ' ')}</strong>
            <span>{finished.length} computed artifacts</span>
          </div>
        ),
      },
      className: 'agent-node tool-node',
    });
    const agents = [
      ...new Set(
        events
          .filter((e) => e.event_type === 'tool.started' && e.metadata.tool === tool)
          .map((e) => e.agent_id),
      ),
    ];
    agents.forEach((agent) => {
      if (agent)
        pairs.set(`${agent}:${tool}`, {
          id: `${agent}:${tool}`,
          source: agent,
          target: `tool:${tool}`,
          label: 'tool call',
          style: { stroke: '#687d68' },
        });
    });
  });
  return (
    <ReactFlow
      nodes={nodes}
      edges={[...pairs.values()]}
      fitView
      fitViewOptions={{ padding: 0.25 }}
      onNodeClick={(_, node) => {
        if (!node.id.startsWith('tool:')) onSelect(node.id);
      }}
      nodesDraggable={false}
      proOptions={{ hideAttribution: true }}
    >
      <FitGraph count={nodes.length} />
      <Background color="#294039" gap={22} />
      <Controls />
    </ReactFlow>
  );
}

function FitGraph({ count }: { count: number }) {
  const initialized = useNodesInitialized();
  const { fitView } = useReactFlow();
  useEffect(() => {
    if (initialized && count) void fitView({ padding: 0.25, duration: 0 });
  }, [initialized, count, fitView]);
  return null;
}
