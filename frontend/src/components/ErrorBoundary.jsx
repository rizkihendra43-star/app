import React from "react";

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, message: error?.message || "Something went wrong" };
  }

  componentDidCatch(error, info) {
    console.error("UI crash:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          data-testid="error-boundary"
          className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-6 text-center text-foreground"
        >
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-destructive/15 text-destructive">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
              <path d="M12 9v4" />
              <path d="M12 17h.01" />
            </svg>
          </div>
          <h1 className="font-display text-2xl font-bold">The app hit a snag</h1>
          <p className="max-w-md text-sm text-muted-foreground">
            Your uploaded files are safe. Reload the page to continue — nothing was lost.
          </p>
          <button
            data-testid="error-reload-btn"
            onClick={() => window.location.reload()}
            className="rounded-xl bg-primary px-5 py-2.5 font-semibold text-primary-foreground transition-transform hover:scale-105"
          >
            Reload app
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
