"use client";

import { useCallback, useEffect, useState } from "react";

import { CapabilityCard, UPCOMING_CAPABILITIES } from "@/components/CapabilityCard";
import { StatusIndicator, toneFromCheck } from "@/components/StatusIndicator";
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

type LoadState = "loading" | "loaded" | "unavailable";

function llmTone(
  llm: LLMStatusResponse | null,
  loading: boolean,
  backendUnavailable: boolean,
): "ok" | "error" | "pending" | "unknown" {
  if (backendUnavailable) {
    return "unknown";
  }
  if (loading || !llm) {
    return "pending";
  }
  if (llm.status === "ready") {
    return "ok";
  }
  if (llm.status === "model_unavailable") {
    return "pending";
  }
  return "error";
}

function embeddingTone(
  emb: EmbeddingStatusResponse | null,
  loading: boolean,
  backendUnavailable: boolean,
): "ok" | "error" | "pending" | "unknown" {
  if (backendUnavailable) return "unknown";
  if (loading || !emb) return "pending";
  if (emb.status === "ready" || emb.model_available) return "ok";
  if (emb.provider_reachable) return "pending";
  return "error";
}

function featureLabel(enabled: boolean | undefined, loaded: boolean): string {
  if (!loaded) return "Checking…";
  if (enabled === undefined) return "Unknown";
  return enabled ? "Available" : "Disabled";
}

export function SystemStatusPanel() {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [info, setInfo] = useState<SystemInfoResponse | null>(null);
  const [llm, setLlm] = useState<LLMStatusResponse | null>(null);
  const [embedding, setEmbedding] = useState<EmbeddingStatusResponse | null>(null);
  const [message, setMessage] = useState<string>("Checking backend…");

  const refresh = useCallback(async () => {
    setLoadState("loading");
    setMessage("Checking backend…");

    const [healthResult, readyResult, infoResult, llmResult, embResult] = await Promise.all([
      fetchHealth(),
      fetchReadiness(),
      fetchSystemInfo(),
      fetchLLMStatus(),
      getEmbeddingStatus(),
    ]);

    if (!healthResult.ok) {
      setHealth(null);
      setReadiness(null);
      setInfo(null);
      setLlm(null);
      setEmbedding(null);
      setLoadState("unavailable");
      setMessage(healthResult.error);
      return;
    }

    setHealth(healthResult.data);
    setReadiness(readyResult.ok ? readyResult.data : null);
    setInfo(infoResult.ok ? infoResult.data : null);
    setLlm(llmResult.ok ? llmResult.data : null);
    setEmbedding(embResult.ok ? embResult.data : null);
    setLoadState("loaded");

    if (!readyResult.ok) {
      setMessage("Backend is reachable but readiness could not be verified.");
    } else if (readyResult.data.status === "not_ready") {
      setMessage("Backend is alive; one or more dependencies are unavailable.");
    } else {
      setMessage("Backend is alive and required dependencies are ready.");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const loading = loadState === "loading";
  const backendUnavailable = loadState === "unavailable";
  const loaded = loadState === "loaded";
  const backendTone =
    loadState === "loading" ? "pending" : loadState === "loaded" ? "ok" : "error";
  const readinessTone =
    loadState === "unavailable"
      ? "error"
      : loading
        ? "pending"
        : readiness?.status === "ready"
          ? "ok"
          : readiness
            ? "error"
            : "unknown";

  return (
    <div className="flex flex-col gap-10" id="system-status" data-testid="system-status-panel">
      <section className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">System status</h2>
            <p className="mt-1 text-sm text-slate-400" data-testid="status-message">
              {message}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void refresh()}
            className="rounded-lg bg-cyan-500/20 px-3 py-2 text-sm font-medium text-cyan-200 ring-1 ring-cyan-400/30 transition hover:bg-cyan-500/30"
          >
            Refresh
          </button>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <StatusIndicator
            label="Backend API"
            tone={backendTone}
            detail={
              loadState === "unavailable"
                ? "Unavailable"
                : health
                  ? `Healthy · liveness ${health.status}`
                  : "Checking…"
            }
          />
          <StatusIndicator
            label="Database"
            tone={
              loadState === "unavailable"
                ? "unknown"
                : toneFromCheck(readiness?.checks.database, loading)
            }
            detail={
              loadState === "unavailable"
                ? "Unavailable"
                : readiness?.checks.database.status === "ok"
                  ? readiness.checks.database.message || "Healthy"
                  : readiness?.checks.database.message ||
                    (loading ? "Checking…" : "Unavailable")
            }
          />
          <StatusIndicator
            label="Redis"
            tone={
              loadState === "unavailable"
                ? "unknown"
                : toneFromCheck(readiness?.checks.redis, loading)
            }
            detail={
              loadState === "unavailable"
                ? "Unavailable"
                : readiness?.checks.redis.status === "ok"
                  ? readiness.checks.redis.message || "Healthy"
                  : readiness?.checks.redis.message ||
                    (loading ? "Checking…" : "Unavailable")
            }
          />
          <StatusIndicator
            label="Overall readiness"
            tone={readinessTone}
            detail={
              loadState === "unavailable"
                ? "Unavailable"
                : readiness?.status === "ready"
                  ? "Healthy"
                  : readiness?.status === "not_ready"
                    ? "Unavailable"
                    : "Checking…"
            }
          />
          <StatusIndicator
            label="Application version"
            tone={info ? "ok" : loading ? "pending" : "unknown"}
            detail={info?.version ?? health?.version ?? "—"}
          />
          <StatusIndicator
            label="Environment"
            tone={info || health ? "ok" : loading ? "pending" : "unknown"}
            detail={info?.environment ?? health?.environment ?? "—"}
          />
        </div>
      </section>

      <section className="flex flex-col gap-4" data-testid="llm-status-section">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">Local LLM &amp; retrieval</h2>
            <p className="mt-1 text-sm text-slate-400">
              Ollama reachability, configured model, and embedding/vector readiness. Core
              readiness does not require models to be pulled.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void refresh()}
            className="rounded-lg bg-slate-500/20 px-3 py-2 text-sm font-medium text-slate-200 ring-1 ring-slate-400/30 transition hover:bg-slate-500/30"
            data-testid="llm-refresh"
          >
            Refresh LLM status
          </button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <StatusIndicator
            label="LLM provider"
            tone={llmTone(llm, loading, backendUnavailable)}
            detail={llm?.provider ?? (backendUnavailable ? "Unavailable" : "Checking…")}
          />
          <StatusIndicator
            label="Configured model"
            tone={llm ? "ok" : loading ? "pending" : "unknown"}
            detail={llm?.model ?? "—"}
          />
          <StatusIndicator
            label="Ollama reachable"
            tone={
              backendUnavailable
                ? "unknown"
                : loading || !llm
                  ? "pending"
                  : llm.provider_reachable
                    ? "ok"
                    : "error"
            }
            detail={
              llm
                ? llm.provider_reachable
                  ? "Healthy"
                  : "Unavailable"
                : backendUnavailable
                  ? "Unavailable"
                  : "Checking…"
            }
          />
          <StatusIndicator
            label="Model available"
            tone={
              backendUnavailable
                ? "unknown"
                : loading || !llm
                  ? "pending"
                  : llm.model_available
                    ? "ok"
                    : llm.provider_reachable
                      ? "pending"
                      : "error"
            }
            detail={
              llm
                ? llm.model_available
                  ? "Available"
                  : llm.provider_reachable
                    ? "Not pulled yet"
                    : "Unavailable"
                : "—"
            }
          />
          <StatusIndicator
            label="RAG vector storage"
            tone={embeddingTone(embedding, loading, backendUnavailable)}
            detail={
              embedding
                ? embedding.model_available || embedding.status === "ready"
                  ? `Available · ${embedding.model}`
                  : embedding.provider_reachable
                    ? "Provider reachable · model not pulled"
                    : "Unavailable"
                : backendUnavailable
                  ? "Unavailable"
                  : "Checking…"
            }
          />
          <StatusIndicator
            label="Agent tools"
            tone={
              backendUnavailable
                ? "unknown"
                : loading
                  ? "pending"
                  : info?.features.tools
                    ? "ok"
                    : "unknown"
            }
            detail={
              backendUnavailable
                ? "Unavailable"
                : featureLabel(info?.features.tools, loaded)
            }
          />
        </div>
        {llm ? (
          <p className="text-xs text-slate-500" data-testid="llm-status-message">
            {llm.message}
          </p>
        ) : null}
      </section>

      <section className="flex flex-col gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Coming later</h2>
          <p className="mt-1 text-sm text-slate-400">
            Cross-conversation memory and voice remain unimplemented.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {UPCOMING_CAPABILITIES.map((capability) => (
            <CapabilityCard key={capability.title} {...capability} />
          ))}
        </div>
        {info ? (
          <p className="text-xs text-slate-500" data-testid="feature-flags">
            API feature flags: ollama={String(info.features.ollama)}, auth=
            {String(info.features.auth)}, rag={String(info.features.rag)}, memory=
            {String(info.features.memory)}, tools={String(info.features.tools)}, voice=
            {String(info.features.voice)}, password_reset_dev_notice=
            {String(Boolean(info.features.password_reset_dev_notice))}
          </p>
        ) : null}
      </section>
    </div>
  );
}
