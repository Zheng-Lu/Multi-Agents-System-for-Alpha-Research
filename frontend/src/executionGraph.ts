import { MarkerType, Position } from '@xyflow/react';
import type { Edge, Node } from '@xyflow/react';
import type { Trace } from './types';

export interface ExecutionNodeData extends Record<string, unknown> {
  kind: 'agent' | 'tool';
  title: string;
  state: string;
  provider?: string;
  model?: string;
  artifacts?: number;
}
export interface ExecutionEdgeData extends Record<string, unknown> {
  kind: 'coordination' | 'feedback' | 'tool';
  title: string;
  count: number;
}
export type ExecutionNode = Node<ExecutionNodeData>;
export type ExecutionEdge = Edge<ExecutionEdgeData, 'smoothstep'> & {
  pathOptions?: { borderRadius: number; offset: number };
};

// Project only recorded execution. Layout and highlighting never create new relationships.
export function executionGraph(events: Trace[]) {
  const terminal = events.findLast(
    (event) => event.event_type.startsWith('run.') && event.event_type !== 'run.started',
  )?.event_type;
  const agents = new Map<string, Trace>();
  for (const event of events) {
    if (event.event_type === 'agent.started' && event.agent_id && !agents.has(event.agent_id))
      agents.set(event.agent_id, event);
  }
  const nodes: ExecutionNode[] = [...agents.keys()].map((id) => {
    const own = events.filter((event) => event.agent_id === id);
    const state = own.some((event) => event.event_type === 'agent.completed')
      ? 'completed'
      : terminal === 'run.cancelled'
        ? 'cancelled'
        : terminal === 'run.completed'
          ? 'completed'
          : terminal
            ? 'failed'
            : own.at(-1)?.status === 'running'
              ? 'running'
              : 'waiting';
    const model = own.findLast((event) => event.model_id);
    return {
      id,
      type: 'execution',
      position: { x: 0, y: 0 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: {
        kind: 'agent',
        title: id.replaceAll('_', ' '),
        state,
        provider: model?.provider_id ?? 'pending',
        model: model?.model_id ?? 'unassigned',
      },
      className: `agent-node ${state}`,
    };
  });
  const edges = new Map<string, ExecutionEdge>();
  function connect(source: string, target: string, kind: ExecutionEdgeData['kind'], title: string) {
    const id = `${kind}:${source}:${target}`;
    const previous = edges.get(id);
    edges.set(id, {
      id,
      source,
      target,
      type: 'smoothstep',
      sourceHandle: kind === 'feedback' ? 'feedback-out' : 'out',
      targetHandle: kind === 'feedback' ? 'feedback-in' : 'in',
      markerEnd: { type: MarkerType.ArrowClosed },
      data: { kind, title, count: (previous?.data?.count ?? 0) + 1 },
      style: {
        stroke: kind === 'tool' ? '#6f8978' : kind === 'feedback' ? '#d6b178' : '#61c4a5',
        strokeDasharray: kind === 'tool' ? '5 5' : undefined,
      },
      pathOptions: { borderRadius: 16, offset: 30 },
    });
  }
  for (const event of events) {
    const type = event.event_type;
    if (!type.startsWith('handoff.') && type !== 'revision.requested') continue;
    const source = type === 'revision.requested' ? 'verifier' : event.agent_id;
    const target =
      type === 'revision.requested' ? 'generator' : String(event.metadata.recipient ?? '');
    if (!source || !agents.has(source) || !agents.has(target)) continue;
    const feedback = type === 'revision.requested' || type === 'handoff.returned';
    const title =
      (
        {
          'handoff.delegated': 'Assign',
          'handoff.returned': 'Findings',
          'handoff.candidate': 'Candidate',
          'revision.requested': 'Revise',
        } as Record<string, string>
      )[type] ?? type;
    connect(source, target, feedback ? 'feedback' : 'coordination', title);
  }
  const tools = [
    ...new Set(
      events.filter((e) => e.event_type === 'tool.started').map((e) => String(e.metadata.tool)),
    ),
  ];
  for (const tool of tools) {
    const own = events.filter((e) => e.metadata.tool === tool);
    const completed = own.filter((e) => e.event_type === 'tool.completed').length;
    const pending = own.filter((e) => e.event_type === 'tool.started').length > completed;
    const state = pending
      ? terminal === 'run.cancelled'
        ? 'cancelled'
        : terminal
          ? 'failed'
          : 'running'
      : 'completed';
    nodes.push({
      id: `tool:${tool}`,
      type: 'execution',
      position: { x: 0, y: 0 },
      data: { kind: 'tool', title: tool.replaceAll('_', ' '), state, artifacts: completed },
      className: `agent-node tool-node ${state}`,
    });
    // Aggregate repeated calls into one real connection with its delivery count.
    for (const event of own) {
      if (event.event_type === 'tool.started' && event.agent_id && agents.has(event.agent_id))
        connect(event.agent_id, `tool:${tool}`, 'tool', 'Tool call');
    }
  }

  // Layer forward handoffs only. Return/verification feedback uses separate top handles.
  const forward = [...edges.values()].filter((e) => e.data?.kind === 'coordination');
  const levels = new Map([...agents.keys()].map((id) => [id, 0]));
  const incoming = new Map([...agents.keys()].map((id) => [id, 0]));
  for (const edge of forward) incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1);
  const queue = [...agents.keys()].filter((id) => incoming.get(id) === 0);
  for (let index = 0; index < queue.length; index++) {
    const source = queue[index];
    for (const edge of forward.filter((e) => e.source === source)) {
      levels.set(
        edge.target,
        Math.max(levels.get(edge.target) ?? 0, (levels.get(source) ?? 0) + 1),
      );
      incoming.set(edge.target, (incoming.get(edge.target) ?? 1) - 1);
      if (incoming.get(edge.target) === 0) queue.push(edge.target);
    }
  }
  const toolColumn = Math.max(0, ...levels.values()) + 1;
  const columns = new Map<number, ExecutionNode[]>();
  for (const node of nodes) {
    const column = node.data.kind === 'tool' ? toolColumn : (levels.get(node.id) ?? 0);
    columns.set(column, [...(columns.get(column) ?? []), node]);
  }
  const rows = Math.max(1, ...[...columns.values()].map((group) => group.length));
  for (const [column, group] of columns) {
    group.forEach((node, index) => {
      node.position = { x: 40 + column * 370, y: 70 + ((rows - group.length) / 2 + index) * 165 };
    });
  }
  return { nodes, edges: [...edges.values()] };
}
