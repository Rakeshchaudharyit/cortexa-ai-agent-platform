"use client";

import { useEffect, useState } from "react";

import { AdminPageHeader } from "@/components/admin/AdminPageHeader";
import { fetchAdminSettings, patchAdminSettings } from "@/services/admin";
import type { AdminSettingItem } from "@/types/admin";

export default function AdminSettingsPage() {
  const [settings, setSettings] = useState<AdminSettingItem[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function reload() {
    const result = await fetchAdminSettings();
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setSettings(result.data.settings);
    const display = result.data.settings.find((s) => s.key === "platform_display_name");
    setDraft(String(display?.value ?? ""));
  }

  useEffect(() => {
    void reload();
  }, []);

  async function save() {
    setError(null);
    setSuccess(null);
    const result = await patchAdminSettings({ platform_display_name: draft });
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setSuccess(`Updated: ${result.data.updated_keys.join(", ")}`);
    await reload();
  }

  return (
    <div data-testid="admin-settings-page">
      <AdminPageHeader
        title="Platform settings"
        description="Only allowlisted safe settings are editable. Secrets and production security flags are blocked."
      />
      <section className="max-w-xl rounded-2xl border border-white/8 bg-slate-900/40 p-4">
        <label className="block text-sm text-slate-300" htmlFor="platform_display_name">
          Platform display name
        </label>
        <input
          id="platform_display_name"
          className="mt-2 w-full rounded-lg border border-white/10 bg-slate-950/70 px-3 py-2 text-sm"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          data-testid="admin-settings-display-name"
        />
        <button
          type="button"
          className="mt-4 rounded-lg bg-cyan-500/20 px-4 py-2 text-sm text-cyan-100 ring-1 ring-cyan-400/30"
          onClick={() => void save()}
          data-testid="admin-settings-save"
        >
          Save
        </button>
        {error ? (
          <p className="mt-3 text-sm text-rose-300" data-testid="admin-settings-error">
            {error}
          </p>
        ) : null}
        {success ? (
          <p className="mt-3 text-sm text-emerald-300" data-testid="admin-settings-success">
            {success}
          </p>
        ) : null}
      </section>
      <section className="mt-6 rounded-2xl border border-white/8 bg-slate-900/40 p-4">
        <h3 className="mb-3 text-sm font-semibold text-white">All safe settings</h3>
        <ul className="space-y-2 text-sm text-slate-300">
          {settings.map((item) => (
            <li key={item.key} className="flex justify-between gap-4 border-b border-white/5 py-2">
              <span>{item.key}</span>
              <span className="text-slate-400">
                {String(item.value)} · {item.source}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
