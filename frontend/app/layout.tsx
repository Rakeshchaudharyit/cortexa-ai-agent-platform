import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AuthProvider } from "@/components/AuthProvider";

import "./globals.css";

export const metadata: Metadata = {
  title: "Cortexa AI Agent Platform",
  description:
    "Secure local AI assistant with authentication, document intelligence, persistent conversations, and auditable agent tools.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
