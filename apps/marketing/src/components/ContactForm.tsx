"use client";

import { useState } from "react";

/**
 * Contact form — client component.
 *
 * POSTs JSON to `/api/contact`, which just logs and returns 200. No email
 * provider is wired. See the route handler for the intentional no-send
 * behavior.
 */
export function ContactForm() {
  const [status, setStatus] = useState<
    "idle" | "submitting" | "success" | "error"
  >("idle");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setStatus("submitting");
    setError(null);

    const data = new FormData(form);
    const body = {
      name: String(data.get("name") ?? "").trim(),
      email: String(data.get("email") ?? "").trim(),
      company: String(data.get("company") ?? "").trim(),
      message: String(data.get("message") ?? "").trim(),
    };

    if (!body.name || !body.email || !body.message) {
      setStatus("error");
      setError("Name, work email, and message are required.");
      return;
    }

    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        setStatus("error");
        setError(`Unexpected response ${res.status}. Please try again.`);
        return;
      }
      form.reset();
      setStatus("success");
    } catch (err) {
      setStatus("error");
      setError(
        err instanceof Error ? err.message : "Network error. Please retry.",
      );
    }
  }

  if (status === "success") {
    return (
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-8 text-emerald-900">
        <h3 className="text-lg font-semibold">Thanks — message received.</h3>
        <p className="mt-2 text-sm">
          We&rsquo;ll be in touch within one business day. If it&rsquo;s
          urgent, email hello@voyagent.globusdemos.com directly.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-5">
      <div className="grid gap-5 md:grid-cols-2">
        <Field name="name" label="Full name" autoComplete="name" required />
        <Field
          name="email"
          label="Work email"
          type="email"
          autoComplete="email"
          required
        />
      </div>
      <Field
        name="company"
        label="Company / agency"
        autoComplete="organization"
      />
      <div>
        <label
          htmlFor="message"
          className="text-sm font-medium text-slate-800"
        >
          How can we help?{" "}
          <span aria-hidden="true" className="text-rose-600">
            *
          </span>
        </label>
        <textarea
          id="message"
          name="message"
          required
          rows={5}
          className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm focus:border-primary"
        />
      </div>
      {error ? (
        <div
          role="alert"
          className="rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800"
        >
          {error}
        </div>
      ) : null}
      <button
        type="submit"
        disabled={status === "submitting"}
        className="inline-flex items-center justify-center rounded-md bg-primary px-6 py-3 text-base font-semibold text-white shadow-soft-md transition hover:bg-primary-600 disabled:opacity-60"
      >
        {status === "submitting" ? "Sending..." : "Send message"}
      </button>
      <p className="text-xs text-slate-500">
        By submitting, you agree to be contacted about Voyagent. We&rsquo;ll
        never share your details.
      </p>
    </form>
  );
}

function Field({
  name,
  label,
  type = "text",
  autoComplete,
  required = false,
}: {
  name: string;
  label: string;
  type?: string;
  autoComplete?: string;
  required?: boolean;
}) {
  return (
    <div>
      <label htmlFor={name} className="text-sm font-medium text-slate-800">
        {label}{" "}
        {required ? (
          <span aria-hidden="true" className="text-rose-600">
            *
          </span>
        ) : null}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        autoComplete={autoComplete}
        required={required}
        className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 shadow-sm focus:border-primary"
      />
    </div>
  );
}
