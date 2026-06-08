import type { Metadata } from "next";
import "./globals.css";
import { ErrorBoundary } from "@/components/error-boundary";
import { ErrorInit } from "@/components/error-init";

export const metadata: Metadata = {
  title: "Hugorm",
  description: "Diarized streaming transcription with graph-grounded refinement.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <ErrorInit />
        <ErrorBoundary>{children}</ErrorBoundary>
      </body>
    </html>
  );
}
