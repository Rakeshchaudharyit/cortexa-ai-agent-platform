"use client";

import { useId, useState, type ChangeEventHandler } from "react";

type PasswordFieldProps = {
  id?: string;
  name: string;
  label: string;
  value: string;
  onChange: ChangeEventHandler<HTMLInputElement>;
  autoComplete: string;
  minLength?: number;
  required?: boolean;
  hint?: string;
  testId?: string;
};

export function PasswordField({
  id,
  name,
  label,
  value,
  onChange,
  autoComplete,
  minLength,
  required = true,
  hint,
  testId,
}: PasswordFieldProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const [visible, setVisible] = useState(false);

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={inputId} className="text-sm font-medium text-slate-200">
        {label}
      </label>
      <div className="relative">
        <input
          id={inputId}
          name={name}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          required={required}
          minLength={minLength}
          value={value}
          onChange={onChange}
          className="w-full rounded-lg border border-white/10 bg-slate-950/40 px-3 py-2 pr-20 text-slate-100 outline-none ring-cyan-400/0 transition focus:ring-2 focus:ring-cyan-400/40"
          data-testid={testId}
        />
        <button
          type="button"
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded px-2 py-1 text-xs font-medium text-cyan-200/90 hover:bg-white/5"
          onClick={() => setVisible((current) => !current)}
          aria-pressed={visible}
          aria-label={visible ? "Hide password" : "Show password"}
          data-testid={testId ? `${testId}-toggle` : undefined}
        >
          {visible ? "Hide" : "Show"}
        </button>
      </div>
      {hint ? <p className="text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}
