import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AuthProvider } from "@/components/AuthProvider";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Cortexa AI Knowledge Platform",
    template: "%s · Cortexa",
  },
  description:
    "Production-oriented enterprise RAG platform with governed knowledge, AI quality evaluation, analytics, feedback review, and durable background operations.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <a href="#main-content" className="cx-skip-link">Skip to main content</a>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
