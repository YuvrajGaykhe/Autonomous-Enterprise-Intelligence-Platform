/**
 * The in-world labels (spec §9.3, D-F-4, AC-F-15): name tags with their bulb glyphs, bubbles and
 * room signs, the locked ones saying which slice opens them, and the layer that places them.
 * They are plain DOM, so they are checked here; the e2e tests see them over the real world.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OrthographicCamera } from 'three';
import { describe, expect, it, vi } from 'vitest';

import { COPY, fill } from '@/copy';
import { seatsFor } from '@/domain/floorPlan';
import { FIXED_AGENTS, ROOMS, connectorAgent } from '@/domain/roster';
import type { WorldAgent } from '@/office/worldTypes';
import { LabelLayer } from '@/world/LabelLayer';
import { labelAnchors, WorldLabels } from '@/world/Overlays';

const roster = [connectorAgent('csv_demo'), ...FIXED_AGENTS];
const agents: WorldAgent[] = roster.map((agent) => ({
  agent,
  state: agent.kind === 'ceo' ? 'WAITING' : agent.kind === 'connector' ? 'ERROR' : 'IDLE',
  bubble: agent.kind === 'ceo' ? 'waiting' : agent.kind === 'linker' ? 'loading' : null,
  detail: '',
}));

function renderLabels() {
  const layer = new LabelLayer();
  const onOpenAgent = vi.fn();
  const onOpenInbox = vi.fn();
  const view = render(
    <WorldLabels
      layer={layer}
      agents={agents}
      onOpenAgent={onOpenAgent}
      onOpenInbox={onOpenInbox}
    />,
  );
  return { ...view, layer, onOpenAgent, onOpenInbox };
}

describe('the labels (§9.3)', () => {
  it('signs every room, each locked room with the slice that opens it', () => {
    const { container } = renderLabels();

    for (const room of ROOMS) {
      const sign = container.querySelector(`[data-room="${room.id}"]`);
      expect(sign).toHaveTextContent(room.name);
      if (room.opensWith !== null) {
        expect(sign).toHaveTextContent(fill(COPY.lockedRoom, { n: room.opensWith }));
      }
    }
    expect(screen.getByText('Opens with VS-02')).toBeInTheDocument();
  });

  it('tags every agent with its bulb glyph, and opens its panel or the inbox on a click', async () => {
    const { container, onOpenAgent, onOpenInbox } = renderLabels();

    const tag = container.querySelector('[data-agent-tag="csv_demo"]');
    expect(tag).toHaveTextContent('!CSV_DEMO_AGENT');
    await userEvent.click(tag as HTMLElement);
    expect(onOpenAgent).toHaveBeenCalledWith('csv_demo');
    await userEvent.click(container.querySelector('[data-agent-tag="ceo"]') as HTMLElement);
    expect(onOpenInbox).toHaveBeenCalledOnce();
  });

  it('shows "?" for a waiting agent, "…" while loading, and nothing otherwise', () => {
    const { container } = renderLabels();

    const bubble = (id: string) => container.querySelector(`[data-label="bubble:${id}"] span`);
    expect(bubble('ceo')).toHaveTextContent('?');
    expect(bubble('linker')).toHaveTextContent('…');
    expect(bubble('memory')).toHaveClass('hidden');
  });

  it('hides the labels from assistive technology: the staff directory is their twin', () => {
    const { container } = renderLabels();

    expect(container.firstElementChild).toHaveAttribute('aria-hidden', 'true');
    for (const tag of container.querySelectorAll('[data-agent-tag]')) {
      expect(tag).toHaveAttribute('tabindex', '-1');
    }
  });
});

describe('the label layer (§9.8)', () => {
  it('anchors a tag and a bubble per agent with a seat, and a sign per room', () => {
    const anchors = labelAnchors(agents, seatsFor(roster));
    expect(anchors.size).toBe(roster.length * 2 + ROOMS.length);
    expect(labelAnchors(agents, new Map()).size).toBe(ROOMS.length);
    const tag = anchors.get('tag:memory');
    const bubble = anchors.get('bubble:memory');
    expect(bubble?.[1]).toBeGreaterThan(tag?.[1] ?? Infinity);
  });

  it('moves each placed label to its anchor on screen, only when it moved', () => {
    const { container, layer } = renderLabels();
    const camera = new OrthographicCamera(-50, 50, 50, -50, 0.1, 100);
    camera.position.set(0, 0, 10);
    camera.lookAt(0, 0, 0);
    camera.updateMatrixWorld();
    layer.anchors.set('tag:memory', [0, 0, 0]);
    layer.anchors.set('tag:linker', [25, 25, 0]);

    layer.project(camera, 200, 100);

    const element = container.querySelector<HTMLElement>('[data-label="tag:memory"]');
    expect(element?.style.transform).toBe('translate3d(100px, 50px, 0)');
    expect(element?.style.visibility).toBe('visible');
    expect(container.querySelector<HTMLElement>('[data-label="tag:linker"]')?.style.transform).toBe(
      'translate3d(150px, 25px, 0)',
    );
    if (element) element.style.transform = 'none';
    layer.project(camera, 200, 100);
    expect(element?.style.transform).toBe('none');
    const unanchored = container.querySelector<HTMLElement>('[data-label="tag:support"]');
    expect(unanchored?.style.visibility).toBe('');
  });

  it('forgets an element once it is gone', () => {
    const { unmount, layer } = renderLabels();
    expect(layer.elements.size).toBeGreaterThan(0);
    unmount();
    expect(layer.elements.size).toBe(0);
    expect(layer.bind('x')).toBe(layer.bind('x'));
  });
});
