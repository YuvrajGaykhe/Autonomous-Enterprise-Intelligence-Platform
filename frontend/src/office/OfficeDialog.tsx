/**
 * The office's panels (spec §8.3, §10): an agent's panel or the CEO inbox as a drawer on the
 * right, a brief as a large overlay. Each is a modal dialog that traps focus while open and, on
 * close, returns it to whatever opened it, or to the office when a deep link opened it.
 */

import { X } from 'lucide-react';
import { Dialog } from 'radix-ui';
import { useLayoutEffect, useRef, type ReactNode } from 'react';

import { cn } from '@/lib/utils';
import { Button } from '@/ui/button';

export function OfficeDialog({
  open,
  title,
  variant,
  onClose,
  returnFocus,
  children,
}: {
  open: boolean;
  title: string;
  variant: 'drawer' | 'overlay';
  onClose: () => void;
  /** Where focus goes on close when the opener is gone or was the page itself. */
  returnFocus: () => HTMLElement | null;
  children: ReactNode;
}) {
  const opener = useRef<HTMLElement | null>(null);
  useLayoutEffect(() => {
    if (open && opener.current === null) {
      const active = document.activeElement;
      opener.current = active instanceof HTMLElement && active !== document.body ? active : null;
    }
  }, [open]);

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/30" />
        <Dialog.Content
          aria-describedby={undefined}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const target = opener.current;
            opener.current = null;
            (target?.isConnected === true ? target : returnFocus())?.focus();
          }}
          className={cn(
            'fixed z-50 flex flex-col bg-background text-foreground shadow-xl',
            variant === 'drawer'
              ? 'inset-y-0 right-0 w-[min(44rem,100vw)] border-l'
              : 'inset-3 mx-auto max-w-6xl rounded-xl border md:inset-6',
          )}
        >
          <div className="flex items-center justify-between gap-4 border-b px-5 py-2">
            <Dialog.Title className="font-pixel text-sm tracking-wide uppercase">
              {title}
            </Dialog.Title>
            <Dialog.Close asChild>
              <Button variant="ghost" size="sm" aria-label="Close">
                <X aria-hidden="true" />
              </Button>
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
