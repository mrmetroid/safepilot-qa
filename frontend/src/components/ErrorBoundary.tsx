import { Component, type ReactNode } from "react";

/** One malformed event must not blank the projector. Show the error and a reload button instead. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="app">
        <div className="error-banner">
          Dashboard error: {this.state.error.message}.{" "}
          <button className="btn btn-primary" onClick={() => location.reload()}>Reload and rejoin run</button>
        </div>
      </div>
    );
  }
}
