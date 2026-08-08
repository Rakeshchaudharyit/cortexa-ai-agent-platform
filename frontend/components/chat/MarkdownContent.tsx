/**
 * MarkdownContent — renders markdown with safe HTML sanitization.
 *
 * Uses react-markdown + rehype-sanitize so no raw HTML or script tags can
 * ever be injected via model output. Code blocks, lists, bold/italic, and
 * external links (target=_blank + rel=noopener) are supported.
 *
 * IMPORTANT: dangerouslySetInnerHTML is NOT used anywhere in this module.
 */
"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import { useCallback, type ReactNode } from "react";

// Merge default schema to ensure anchors can have target/rel.
const sanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    a: [...(defaultSchema.attributes?.a ?? []), "target", "rel"],
  },
};

type Props = {
  content: string;
  /** Optional className for the container. */
  className?: string;
};

export function MarkdownContent({ content, className }: Props) {
  const renderLink = useCallback(
    ({ href, children }: { href?: string; children?: ReactNode }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-cyan-300 underline underline-offset-2 hover:text-cyan-200"
      >
        {children}
      </a>
    ),
    [],
  );

  const renderCode = useCallback(
    ({
      className: langClass,
      children,
    }: {
      className?: string;
      children?: ReactNode;
    }) => {
      const isBlock = langClass?.startsWith("language-");
      if (isBlock) {
        return (
          <pre className="my-2 overflow-x-auto cx-scrollbar rounded-lg bg-slate-950/60 p-3 text-xs text-slate-200 ring-1 ring-white/10">
            <code className={langClass}>{children}</code>
          </pre>
        );
      }
      return (
        <code className="rounded bg-slate-800/80 px-1 py-0.5 text-xs text-cyan-200">
          {children}
        </code>
      );
    },
    [],
  );

  return (
    <div
      className={`prose-sm prose prose-invert max-w-none leading-relaxed ${className ?? ""}`}
      data-testid="markdown-content"
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypeSanitize, sanitizeSchema]]}
        components={{
          a: renderLink,
          code: renderCode,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
