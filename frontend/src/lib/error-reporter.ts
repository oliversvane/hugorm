"use client";
import { apiBaseUrl } from "./api";

type Payload = {
  message: string;
  stack?: string;
  url?: string;
  context?: Record<string, unknown>;
};

async function send(payload: Payload): Promise<void> {
  try {
    await fetch(`${apiBaseUrl()}/client-errors`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: payload.message.slice(0, 4000),
        stack: payload.stack?.slice(0, 20000),
        url: payload.url ?? window.location.href,
        user_agent: navigator.userAgent,
        context: payload.context ?? {},
      }),
      keepalive: true,
    });
  } catch {
    // Never let the reporter itself raise — dropping a log is fine.
  }
}

let installed = false;

export function installErrorReporter(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;

  window.addEventListener("error", (e) => {
    send({
      message: e.message || "window.error",
      stack: e.error instanceof Error ? e.error.stack : undefined,
      context: { filename: e.filename, lineno: e.lineno, colno: e.colno },
    });
  });

  window.addEventListener("unhandledrejection", (e) => {
    const reason = e.reason;
    send({
      message:
        reason instanceof Error ? reason.message : `unhandled rejection: ${String(reason)}`,
      stack: reason instanceof Error ? reason.stack : undefined,
    });
  });
}

export function reportClientError(
  message: string,
  stack?: string,
  context?: Record<string, unknown>,
): void {
  send({ message, stack, context });
}
