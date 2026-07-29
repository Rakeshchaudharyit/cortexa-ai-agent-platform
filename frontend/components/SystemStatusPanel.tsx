"use client";

import { useCallback, useEffect, useState } from "react";

import { CapabilityCard, PLANNED_CAPABILITIES } from "@/components/CapabilityCard";
import { StatusIndicator, toneFromCheck } from "@/components/StatusIndicator";
import {
  fetchHealth,
  fetchLLMStatus,
  fetchReadiness,
  fetchSystemInfo,
} from "@/services/system";
import type {
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

export function SystemStatusPanel() {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [readiness, setReadiness] = useState<ReadinessResponse | null>(null);
  const [info, setInfo] = useState<SystemInfoResponse | null>(null);
  const [llm, setLlm] = useState<LLMStatusResponse | null>(null);
  const [message, setMessage] = useState<string>("Checking backend…");

  const refresh = useCallback(async () => {
    setLoadState("loading");
    setMessage("Checking backend…");

    const [healthResult, readyResult, infoResult, llmResult] = await Promise.all([
      fetchHealth(),
      fetchReadiness(),
      fetchSystemInfo(),
      fetchLLMStatus(),
    ]);

    if (!healthResult.ok) {
      setHealth(null);
      setReadiness(null);
      setInfo(null);
      setLlm(null);
      setLoadState("unavailable");
      setMessage(healthResult.error);
      return;
    }

    setHealth(healthResult.data);
    setReadiness(readyResult.ok ? readyResult.data : null);
    setInfo(infoResult.ok ? infoResult.data : null);
    setLlm(llmResult.ok ? llmResult.data : null);
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
    <div className="flex flex-col gap-10">
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
                ? "Unreachable"
                : health
                  ? `Liveness ${health.status}`
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
                ? "Unknown — backend offline"
                : readiness?.checks.database.message ||
                  (readiness?.checks.database.status === "ok" ? "Reachable" : "Checking…")
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
                ? "Unknown — backend offline"
                : readiness?.checks.redis.message ||
                  (readiness?.checks.redis.status === "ok" ? "Reachable" : "Checking…")
            }
          />
          <StatusIndicator
            label="Overall readiness"
            tone={readinessTone}
            detail={
              loadState === "unavailable"
                ? "Not verified"
                : readiness?.status === "ready"
                  ? "Ready"
                  : readiness?.status === "not_ready"
                    ? "Not ready"
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
            <h2 className="text-lg font-semibold text-slate-100">Local LLM status</h2>
            <p className="mt-1 text-sm text-slate-400">
              Ollama provider reachability and configured model availability. Core readiness
              does not require the model to be pulled.
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
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatusIndicator
            label="LLM provider"
            tone={llmTone(llm, loading, backendUnavailable)}
            detail={llm?.provider ?? (backendUnavailable ? "Unknown" : "Checking…")}
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
                  ? "Reachable"
                  : "Unreachable"
                : backendUnavailable
                  ? "Unknown — backend offline"
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
                  ? "Installed"
                  : llm.provider_reachable
                    ? "Not pulled yet"
                    : "Unknown"
                : "—"
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
          <h2 className="text-lg font-semibold text-slate-100">Planned capabilities</h2>
          <p className="mt-1 text-sm text-slate-400">
            Chat UI, RAG, memory, tools, and voice remain unavailable in Phase 3.
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {PLANNED_CAPABILITIES.map((capability) => (
            <CapabilityCard key={capability.title} {...capability} />
          ))}
        </div>
        {info ? (
          <p className="text-xs text-slate-500" data-testid="feature-flags">
            API feature flags: ollama={String(info.features.ollama)}, auth=
            {String(info.features.auth)}, rag={String(info.features.rag)}, memory=
            {String(info.features.memory)}, tools={String(info.features.tools)}, voice=
            {String(info.features.voice)}
          </p>
        ) : null}
      </section>
    </div>
  );
}
