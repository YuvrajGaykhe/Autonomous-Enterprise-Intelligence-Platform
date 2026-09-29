/** A world that throws (no WebGL, a lost device) reports it once and renders nothing (§9.11). */

import { Component, type ReactNode } from 'react';

interface Props {
  onFailure: (error: unknown) => void;
  children: ReactNode;
}

export class WorldBoundary extends Component<Props, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  override componentDidCatch(error: unknown): void {
    this.props.onFailure(error);
  }

  override render(): ReactNode {
    return this.state.failed ? null : this.props.children;
  }
}
