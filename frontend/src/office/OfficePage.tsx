/**
 * The office (D-F-6, spec §8.1, §9): the home screen. It serves `/`, `/?agent=<id>`,
 * `/?inbox=1` and `/brief/<id>`, and stays mounted across them, so the 3D world is created once.
 *
 * The world is a lazy chunk that only this page loads (§9.10). The page checks for WebGL first and
 * sends a reader whose device cannot start it, or whose context was lost twice, to the Classic twin
 * of the same address with the fallback notice (§9.11). A reader who chose Classic view goes there
 * too. The panels, the staff directory and the view controls are HTML over the canvas.
 */

import { lazy, Suspense, useCallback, useEffect, useId, useRef, useState } from 'react';
import { Navigate, useLocation, useMatch, useNavigate } from 'react-router';

import { useRoster } from '@/data/useRoster';
import { agentById } from '@/domain/roster';
import {
  addressOf,
  flag,
  officeTarget,
  pixelArt,
  rememberedView,
  twinAddress,
  type Target,
} from '@/domain/views';
import { yawDegrees } from '@/domain/officeCamera';
import { useReducedMotion } from '@/lib/motion';
import { STORAGE_KEYS, readStored } from '@/lib/storage';
import { canCreateWebGL } from '@/lib/webgl';
import { AgentPanel } from '@/panels/AgentPanel';
import { BriefDetail } from '@/panels/BriefDetail';
import { CeoInbox } from '@/panels/CeoInbox';
import { useCamera } from '@/state/camera';
import { usePreferences } from '@/state/preferences';
import { useSession } from '@/state/session';
import { EmptyState, LoadingState } from '@/states/states';
import { ROLE_LINES } from '@/copy';

import { CameraControls, CONTROLS_HELP, useCameraKeys, useViewportPointer } from './CameraControls';
import { OfficeDialog } from './OfficeDialog';
import { OfficeText } from './OfficeText';
import { StaffDirectory } from './StaffDirectory';
import { useOfficeModel } from './useOfficeModel';
import { WorldBoundary } from './WorldBoundary';

const World = lazy(() => import('@/world/Office'));

/** How long a desk stays highlighted after an evidence link opened (§8.4). */
export const HIGHLIGHT_MS = 10_000;

export function OfficePage() {
  const { pathname, search } = useLocation();
  const [preferred] = useState(() => rememberedView(readStored(STORAGE_KEYS.view)));
  const [webgl] = useState(canCreateWebGL);
  const failed = useSession((state) => state.webglFailed);
  if (preferred === 'classic') {
    return <Navigate to={twinAddress('classic', pathname, search)} replace />;
  }
  if (failed || !webgl) return <FallBack />;
  return <Office />;
}

/** No WebGL, or a failed world: Classic view, with the notice (§9.11). */
function FallBack() {
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const failWebgl = useSession((state) => state.failWebgl);
  useEffect(() => {
    failWebgl();
    void navigate(twinAddress('classic', pathname, search), { replace: true });
  }, [failWebgl, navigate, pathname, search]);
  return <LoadingState label="Classic view" />;
}

function Office() {
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const briefMatch = useMatch('/brief/:briefId');
  const target: Target = officeTarget(pathname, search) ?? { kind: 'home' };
  const params = new URLSearchParams(search);

  const model = useOfficeModel();
  const { roster, sources } = useRoster();
  const storedPixel = usePreferences((state) => state.pixel);
  const pixel = pixelArt(params.get('pixel'), storedPixel ? '1' : '0');
  const still = flag(params.get('still'));
  const perf = flag(params.get('perf'));
  const reducedMotion = useReducedMotion();
  const quarterTurns = useCamera((state) => state.quarterTurns);
  const zoomIndex = useCamera((state) => state.zoomIndex);

  const highlighted = useSession((state) => state.highlightedAgentId);
  const highlight = useSession((state) => state.highlight);
  const failWebgl = useSession((state) => state.failWebgl);
  const loseContext = useSession((state) => state.loseContext);
  const [ready, setReady] = useState(false);
  const viewport = useRef<HTMLDivElement>(null);
  const helpId = useId();
  const pointer = useViewportPointer();
  useCameraKeys();

  useEffect(() => {
    if (highlighted === null) return undefined;
    const timer = window.setTimeout(() => highlight(null), HIGHLIGHT_MS);
    return () => window.clearTimeout(timer);
  }, [highlighted, highlight]);

  const go = useCallback(
    (to: Target) => void navigate(addressOf('office', to, search)),
    [navigate, search],
  );
  const close = useCallback(() => go({ kind: 'home' }), [go]);
  const openAgent = useCallback((agentId: string) => go({ kind: 'agent', agentId }), [go]);
  const openInbox = useCallback(() => go({ kind: 'inbox' }), [go]);
  const onReady = useCallback(() => setReady(true), []);
  const returnFocus = useCallback(() => viewport.current, []);

  const agentId = target.kind === 'agent' ? target.agentId : null;
  const agent = agentId === null ? null : agentById(roster, agentId);

  return (
    <div
      data-testid="office"
      data-world={ready ? 'ready' : 'loading'}
      data-yaw={yawDegrees(quarterTurns)}
      data-zoom={zoomIndex}
      data-pixel={pixel ? '1' : '0'}
      data-highlight={highlighted ?? ''}
      className="flex h-full overflow-hidden"
    >
      <StaffDirectory
        agents={model.agents}
        search={search}
        openAgentId={agentId}
        inboxOpen={target.kind === 'inbox'}
        loadingConnectors={sources.isPending}
      />
      <div className="relative min-w-0 flex-1 bg-[#2b2622]">
        <div
          ref={viewport}
          role="region"
          aria-label="3D office"
          aria-describedby={helpId}
          tabIndex={-1}
          className="absolute inset-0 touch-none outline-none"
          {...pointer}
        >
          <WorldBoundary onFailure={failWebgl}>
            <Suspense
              fallback={
                <div className="grid h-full place-items-center">
                  <div className="w-64">
                    <LoadingState label="the 3D office" />
                  </div>
                </div>
              }
            >
              <World
                agents={model.agents}
                board={model.board}
                trayCount={model.trayCount}
                notes={model.notes}
                openAgentId={agentId ?? (target.kind === 'inbox' ? 'ceo' : null)}
                highlightedAgentId={highlighted}
                pixel={pixel}
                still={still}
                perf={perf}
                reducedMotion={reducedMotion}
                onOpenAgent={openAgent}
                onOpenInbox={openInbox}
                onReady={onReady}
                onContextLost={loseContext}
              />
            </Suspense>
          </WorldBoundary>
        </div>
        <CameraControls />
      </div>
      <p id={helpId} className="sr-only">
        {CONTROLS_HELP}
      </p>
      <OfficeText board={model.board} notes={model.notes} />

      <OfficeDialog
        open={agentId !== null}
        title={agent === null ? 'Agent' : agent.tag}
        variant="drawer"
        onClose={close}
        returnFocus={returnFocus}
      >
        {agent !== null ? (
          <AgentPanel agent={agent} />
        ) : sources.isPending ? (
          <LoadingState label="the agent roster" />
        ) : (
          <EmptyState message={`No agent named ${agentId ?? ''} works in this office.`} />
        )}
      </OfficeDialog>
      <OfficeDialog
        open={target.kind === 'inbox'}
        title="CEO inbox"
        variant="drawer"
        onClose={close}
        returnFocus={returnFocus}
      >
        <div className="space-y-4">
          <p className="text-sm">{ROLE_LINES.ceo}</p>
          <CeoInbox />
        </div>
      </OfficeDialog>
      <OfficeDialog
        open={briefMatch !== null}
        title="Brief"
        variant="overlay"
        onClose={close}
        returnFocus={returnFocus}
      >
        {briefMatch !== null && (
          <BriefDetail
            key={briefMatch.params.briefId}
            briefId={briefMatch.params.briefId ?? ''}
            inboxHref={addressOf('office', { kind: 'inbox' }, search)}
          />
        )}
      </OfficeDialog>
    </div>
  );
}
