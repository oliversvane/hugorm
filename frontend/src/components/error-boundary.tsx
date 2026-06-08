"use client";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { reportClientError } from "@/lib/error-reporter";

type State = { error: Error | null };

export class ErrorBoundary extends Component<
  { children: ReactNode; fallback?: ReactNode },
  State
> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    reportClientError(error.message, error.stack, {
      component_stack: info.componentStack ?? "",
      type: "react_error_boundary",
    });
  }

  reset = () => this.setState({ error: null });

  render() {
    if (this.state.error) {
      return (
        this.props.fallback ?? (
          <div className="m-6 p-4 bg-red-50 border border-red-200 rounded text-sm">
            <div className="font-medium text-red-800">Something went wrong</div>
            <div className="text-red-700 mt-1 break-all">
              {this.state.error.message}
            </div>
            <button
              type="button"
              onClick={this.reset}
              className="mt-2 text-xs text-red-700 underline"
            >
              Try again
            </button>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
