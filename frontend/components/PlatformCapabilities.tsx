"use client";

import { useCallback, useEffect, useState } from "react";

import { CapabilityCard, type CapabilityStatus } from "@/components/CapabilityCard";
import { getEmbeddingStatus } from "@/services/documents";
import {
  fetchHealth,
  fetchLLMStatus,
  fetchReadiness,
  fetchSystemInfo,
} from "@/services/system";
import type {
  EmbeddingStatusResponse,
  HealthResponse,
  LLMStatusResponse,
  ReadinessResponse,
  SystemInfoResponse,
} from "@/types/api";

type CapabilityItem = {
  key: string;
  title: string;
  description: string;
  secondary?: string;
  status: CapabilityStatus;
  testId: string;
};

function llmCapabilityStatus(llm: LLMStatusResponse | null, loaded: boolean): CapabilityStatus {
  if (!loaded) return "available";
  if (!llm) return "unavailable";
  if (llm.status === "ready") return "online";
  if (llm.status === "model_unavailable") return "available";
  return "unavailable";
}

function llmDetails(llm: LLMStatusResponse | null, loaded: boolean): string {
  if (!loaded) return "Checking status…";
  if (!llm) return "Status unavailable";
  const provider = llm.provider || "ollama";
  const model = llm.model || "—";
  return `${provider} · ${model}`;
}

function embeddingCapabilityStatus(
  emb: EmbeddingStatusResponse | null,
  loaded: boolean,
): CapabilityStatus {
  if (!loaded) return "available";
  if (!emb) return "unavailable";
  if (emb.status === "ready" || emb.model_available) return "online";
  if (emb.provider_reachable) return "available";
  return "unavailable";
}

function toolsStatus(info: SystemInfoResponse | null, loaded: boolean): CapabilityStatus {
  if (!loaded) return "available";
  if (!info) return "unavailable";
  return info.features.tools ? "available" : "disabled";
}

function infraStatus(
  health: HealthResponse | null,
  readiness: ReadinessResponse | null,
  loaded: boolean,
): CapabilityStatus {
  if (!loaded) return "available";
  if (!health) return "unavailable";
  if (readiness?.status === "ready") return "healthy";
  if (readiness?.status === "not_ready") return "unavailable";
  return "available";
}

export function PlatformCapabilities() {
  const [loaded, setLoaded] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [info, setInfo] = useState<SystemInfoResponse | null>(null);
  const [llm, setLlm] = useState<LLMStatusResponse | null>(null);
  const [embedding, setEmbedding] = useState<EmbeddingStatusResponse | null>(null);

  const refresh = useCallback(async () => {
    const [healthResult, readyResult, infoResult, llmResult, embResult] = await Promise.all([
      fetchHealth(),
      fetchReadiness(),
      fetchSystemInfo(),
      fetchLLMStatus(),
      getEmbeddingStatus(),
    ]);

    setHealth(healthResult.ok ? healthResult.data : null);
    setReadiness(readyResult.ok ? readyResult.data : null);
    setInfo(infoResult.ok ? infoResult.data : null);
    setLlm(llmResult.ok ? llmResult.data : null);
    setEmbedding(embResult.ok ? embResult.data : null);
    setLoaded(true);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const authAvailable = !loaded ? "available" : info?.features.auth ? "available" : "disabled";
  const ragAvailable = !loaded
    ? "available"
    : info?.features.rag
      ? embeddingCapabilityStatus(embedding, loaded)
      : "disabled";

  const items: CapabilityItem[] = [
    {
      key: "ai-model",
      title: "Local AI Model",
      description: llmDetails(llm, loaded),
      secondary: "Private local inference with streaming responses",
      status: llmCapabilityStatus(llm, loaded),
      testId: "capability-ai-model",
    },
    {
      key: "auth",
      title: "Secure Authentication",
      description: "JWT access tokens · HttpOnly refresh sessions",
      status: authAvailable,
      testId: "capability-auth",
    },
    {
      key: "documents",
      title: "Document Intelligence",
      description: "Upload, processing, embeddings, and ownership controls",
      status: info?.features.rag ? "available" : loaded ? "disabled" : "available",
      testId: "capability-documents",
    },
    {
      key: "rag",
      title: "Knowledge Retrieval",
      description: "pgvector search with grounded responses and citations",
      status: ragAvailable,
      testId: "capability-rag",
    },
    {
      key: "conversations",
      title: "Persistent Conversations",
      description: "Multi-turn chat, streaming, history, and ownership",
      status: "available",
      testId: "capability-conversations",
    },
    {
      key: "agent-tools",
      title: "Agent Tools",
      description: "Calculator, date/time, knowledge search, and conversation summary",
      status: toolsStatus(info, loaded),
      testId: "capability-agent-tools",
    },
    {
      key: "tool-auditing",
      title: "Execution History",
      description: "Persistent tool status, duration, safe arguments, and results",
      status: toolsStatus(info, loaded),
      testId: "capability-tool-auditing",
    },
    {
      key: "infrastructure",
      title: "Platform Infrastructure",
      description: "FastAPI · Next.js · PostgreSQL · Redis · Docker",
      status: infraStatus(health, readiness, loaded),
      testId: "capability-infrastructure",
    },
  ];

  return (
    <section className="flex flex-col gap-4" data-testid="platform-capabilities" id="capabilities">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Platform capabilities</h2>
          <p className="mt-1 text-sm text-slate-400">
            Live where health endpoints exist; otherwise marked Available when the feature is
            shipped.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void refresh()}
          className="rounded-lg bg-slate-500/20 px-3 py-2 text-sm font-medium text-slate-200 ring-1 ring-slate-400/30 transition hover:bg-slate-500/30"
        >
          Refresh
        </button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {items.map((item) => (
          <CapabilityCard
            key={item.key}
            title={item.title}
            description={item.description}
            secondary={item.secondary}
            status={item.status}
            testId={item.testId}
          />
        ))}
      </div>
    </section>
  );
}
