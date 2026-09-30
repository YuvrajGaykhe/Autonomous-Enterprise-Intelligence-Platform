/**
 * The three-step tour (spec §8.2, F6) and the HUD's "?" that opens it. The tour is a modal dialog
 * over either view. Each step lifts the part of the page it describes above the dimmed page and
 * rings it (`data-tour-spot`, styled in the theme). Closing it, by any means, marks it seen in this
 * browser.
 */

import { CircleHelp, X } from 'lucide-react';
import { Dialog } from 'radix-ui';
import { useEffect, useLayoutEffect, useRef } from 'react';

import { TOUR_STEPS, type TourSpot } from '@/domain/tour';
import { PixelArt, type ArtName } from '@/states/art';
import { useTour } from '@/state/tour';
import { Button } from '@/ui/button';

const ART_OF: Readonly<Record<TourSpot, ArtName>> = {
  agents: 'agent',
  run: 'desk',
  inbox: 'stamp',
};

export function TourButton() {
  const start = useTour((state) => state.start);
  return (
    <Button variant="outline" size="sm" onClick={start}>
      <CircleHelp aria-hidden="true" />
      Tour
    </Button>
  );
}

export function Tour() {
  const open = useTour((state) => state.open);
  const index = useTour((state) => state.step);
  const move = useTour((state) => state.move);
  const close = useTour((state) => state.close);
  const primary = useRef<HTMLButtonElement>(null);
  // Radix returns focus only to a Dialog.Trigger; the HUD's Tour is not one, so remember the opener.
  const opener = useRef<HTMLElement | null>(null);
  useLayoutEffect(() => {
    if (open && opener.current === null) {
      const active = document.activeElement;
      opener.current = active instanceof HTMLElement && active !== document.body ? active : null;
    }
  }, [open]);
  const step = TOUR_STEPS[index] ?? TOUR_STEPS[0];
  const last = index === TOUR_STEPS.length - 1;

  // Moving between steps replaces the buttons; keep the focus on the step's main action.
  useEffect(() => {
    if (open) primary.current?.focus();
  }, [open, index]);

  if (step === undefined) return null;
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) close();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Dialog.Content
          data-testid="tour"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            primary.current?.focus();
          }}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const target = opener.current;
            opener.current = null;
            if (target?.isConnected === true) target.focus();
          }}
          className="fixed inset-x-4 bottom-4 z-50 mx-auto max-w-md rounded-xl border bg-card p-5 text-foreground shadow-xl md:top-1/3 md:bottom-auto"
        >
          <div className="flex gap-4">
            <PixelArt name={ART_OF[step.spot]} className="h-16 shrink-0" />
            <div className="min-w-0 space-y-1.5">
              <p className="font-pixel text-xs tracking-wide text-muted-foreground uppercase">
                {`Tour · step ${index + 1} of ${TOUR_STEPS.length}`}
              </p>
              <Dialog.Title className="text-lg font-semibold">{step.title}</Dialog.Title>
              <Dialog.Description className="text-sm">{step.body}</Dialog.Description>
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between gap-3">
            <ol aria-hidden="true" className="flex gap-1.5">
              {TOUR_STEPS.map((each, at) => (
                <li
                  key={each.spot}
                  className={
                    at === index ? 'size-2 rounded-full bg-primary' : 'size-2 rounded-full bg-muted'
                  }
                />
              ))}
            </ol>
            <div className="flex gap-2">
              {index > 0 && (
                <Button variant="ghost" size="sm" onClick={() => move(-1)}>
                  Back
                </Button>
              )}
              {last ? (
                <Button ref={primary} size="sm" onClick={close}>
                  Start exploring
                </Button>
              ) : (
                <Button ref={primary} size="sm" onClick={() => move(1)}>
                  Next
                </Button>
              )}
            </div>
          </div>
          <Dialog.Close asChild>
            <Button
              variant="ghost"
              size="sm"
              aria-label="Close the tour"
              className="absolute top-2 right-2"
            >
              <X aria-hidden="true" />
            </Button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
