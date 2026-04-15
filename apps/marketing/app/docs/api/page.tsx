/**
 * Public API reference page — /docs/api.
 *
 * Server component that fetches the live FastAPI OpenAPI JSON at
 * request time and renders a minimal, readable reference. We
 * intentionally hand-roll the renderer instead of pulling in Redoc or
 * Scalar — it's ~150 lines, zero dependencies, and the OpenAPI tree
 * we care about (paths + operations + parameters + responses) is
 * flat enough to iterate directly.
 *
 * Caching: Next's ``fetch`` cache is set to 1 hour. The upstream
 * schema changes at most once per deploy; stale-for-an-hour is fine.
 *
 * Failure mode: if the fetch fails (network, non-200, invalid JSON)
 * we render a friendly "temporarily unavailable" panel instead of
 * throwing. The page is part of the public marketing surface — it
 * must never 500.
 */
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "API reference · Voyagent",
  description:
    "The full voyagent HTTP API — every endpoint, parameter, and response shape, rendered directly from our live OpenAPI schema.",
};

// Next.js caches this page at the route level for one hour.
export const revalidate = 3600;

const OPENAPI_URL =
  process.env.NEXT_PUBLIC_API_OPENAPI_URL ??
  "https://voyagent.globusdemos.com/api/openapi.json";

type OpenApiParameter = {
  name: string;
  in: string;
  required?: boolean;
  description?: string;
  schema?: { type?: string };
};

type OpenApiOperation = {
  summary?: string;
  description?: string;
  tags?: string[];
  operationId?: string;
  parameters?: OpenApiParameter[];
  requestBody?: {
    description?: string;
    required?: boolean;
    content?: Record<string, { schema?: unknown }>;
  };
  responses?: Record<
    string,
    { description?: string; content?: Record<string, unknown> }
  >;
};

type OpenApiDoc = {
  info?: { title?: string; version?: string; description?: string };
  paths?: Record<string, Record<string, OpenApiOperation>>;
};

const HTTP_METHODS = [
  "get",
  "post",
  "put",
  "patch",
  "delete",
  "options",
  "head",
] as const;
type HttpMethod = (typeof HTTP_METHODS)[number];

function isHttpMethod(m: string): m is HttpMethod {
  return (HTTP_METHODS as readonly string[]).includes(m);
}

/**
 * Turn "/auth/sign-in" into "auth-sign-in" so the anchor is stable
 * and URL-safe. Curly-braced path params become the bare name.
 */
function anchorFor(path: string, method: string): string {
  const slug = path
    .replace(/[{}]/g, "")
    .replace(/^\/+/, "")
    .replace(/\/+/g, "-")
    .replace(/[^a-z0-9-]/gi, "-")
    .toLowerCase();
  return `${method}-${slug || "root"}`;
}

async function fetchOpenApi(): Promise<OpenApiDoc | null> {
  try {
    const res = await fetch(OPENAPI_URL, {
      next: { revalidate: 3600 },
      headers: { accept: "application/json" },
    });
    if (!res.ok) return null;
    const body = (await res.json()) as OpenApiDoc;
    if (!body || typeof body !== "object") return null;
    return body;
  } catch {
    return null;
  }
}

const METHOD_COLORS: Record<string, string> = {
  get: "#059669",
  post: "#2563eb",
  put: "#ea580c",
  patch: "#ca8a04",
  delete: "#dc2626",
  options: "#6b7280",
  head: "#6b7280",
};

export default async function ApiReferencePage() {
  const doc = await fetchOpenApi();

  if (!doc || !doc.paths) {
    return (
      <main
        style={{
          maxWidth: 960,
          margin: "0 auto",
          padding: "48px 24px",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <h1 style={{ fontSize: 32, marginBottom: 8 }}>API reference</h1>
        <p
          data-testid="api-docs-unavailable"
          style={{
            padding: "16px 18px",
            borderRadius: 10,
            background: "#fef2f2",
            border: "1px solid #fecaca",
            color: "#991b1b",
            fontSize: 14,
          }}
        >
          API reference temporarily unavailable. Please try again shortly.
        </p>
      </main>
    );
  }

  // Flatten paths → [path, method, operation] tuples and sort by path
  // so the output is stable across renders.
  const entries: Array<{
    path: string;
    method: HttpMethod;
    op: OpenApiOperation;
  }> = [];
  for (const [path, methods] of Object.entries(doc.paths)) {
    if (!methods) continue;
    for (const [method, op] of Object.entries(methods)) {
      if (!isHttpMethod(method)) continue;
      entries.push({ path, method, op });
    }
  }
  entries.sort((a, b) =>
    a.path === b.path ? a.method.localeCompare(b.method) : a.path.localeCompare(b.path),
  );

  return (
    <main
      style={{
        maxWidth: 960,
        margin: "0 auto",
        padding: "48px 24px 96px",
        fontFamily: "system-ui, sans-serif",
        color: "#18181b",
      }}
    >
      <header style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 36, margin: 0, letterSpacing: -0.5 }}>
          {doc.info?.title ?? "Voyagent API"}
        </h1>
        <p style={{ marginTop: 8, color: "#52525b", fontSize: 15 }}>
          Every endpoint the voyagent platform exposes, rendered directly
          from our live OpenAPI schema
          {doc.info?.version ? ` (v${doc.info.version})` : ""}.
        </p>
        <p
          data-testid="api-docs-count"
          style={{ marginTop: 4, color: "#71717a", fontSize: 13 }}
        >
          {entries.length} endpoints
        </p>
      </header>

      <nav
        aria-label="Endpoints"
        data-testid="api-docs-index"
        style={{
          marginBottom: 32,
          padding: 16,
          background: "#fafafa",
          border: "1px solid #e5e7eb",
          borderRadius: 10,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
          gap: 6,
          fontSize: 12,
          fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        }}
      >
        {entries.map(({ path, method }) => (
          <a
            key={`${method}-${path}`}
            href={`#${anchorFor(path, method)}`}
            style={{
              color: "#27272a",
              textDecoration: "none",
              display: "flex",
              gap: 8,
              alignItems: "baseline",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            <span
              style={{
                color: METHOD_COLORS[method] ?? "#6b7280",
                fontWeight: 700,
                textTransform: "uppercase",
                fontSize: 10,
                minWidth: 42,
              }}
            >
              {method}
            </span>
            <span>{path}</span>
          </a>
        ))}
      </nav>

      <section data-testid="api-docs-endpoints">
        {entries.map(({ path, method, op }) => {
          const id = anchorFor(path, method);
          const params = op.parameters ?? [];
          const responses = Object.entries(op.responses ?? {});
          return (
            <article
              key={id}
              id={id}
              data-testid={`api-endpoint-${id}`}
              style={{
                marginBottom: 28,
                padding: 20,
                background: "#fff",
                border: "1px solid #e5e7eb",
                borderRadius: 12,
                scrollMarginTop: 24,
              }}
            >
              <h2
                style={{
                  fontSize: 15,
                  margin: 0,
                  fontFamily:
                    "ui-monospace, SFMono-Regular, Menlo, monospace",
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  flexWrap: "wrap",
                }}
              >
                <span
                  style={{
                    padding: "3px 8px",
                    borderRadius: 6,
                    background: "#f4f4f5",
                    color: METHOD_COLORS[method] ?? "#6b7280",
                    fontSize: 11,
                    fontWeight: 700,
                    textTransform: "uppercase",
                  }}
                >
                  {method}
                </span>
                <span>{path}</span>
              </h2>
              {op.summary ? (
                <p style={{ marginTop: 10, marginBottom: 0, fontSize: 14 }}>
                  {op.summary}
                </p>
              ) : null}
              {op.description && op.description !== op.summary ? (
                <p
                  style={{
                    marginTop: 8,
                    marginBottom: 0,
                    fontSize: 13,
                    color: "#52525b",
                    lineHeight: 1.55,
                  }}
                >
                  {op.description}
                </p>
              ) : null}

              {params.length > 0 ? (
                <div style={{ marginTop: 14 }}>
                  <h3
                    style={{
                      fontSize: 11,
                      textTransform: "uppercase",
                      letterSpacing: 0.5,
                      color: "#71717a",
                      margin: "0 0 6px 0",
                    }}
                  >
                    Parameters
                  </h3>
                  <ul
                    style={{
                      margin: 0,
                      padding: 0,
                      listStyle: "none",
                      fontSize: 13,
                    }}
                  >
                    {params.map((p) => (
                      <li
                        key={`${p.in}-${p.name}`}
                        style={{ padding: "4px 0", color: "#3f3f46" }}
                      >
                        <code
                          style={{
                            fontFamily:
                              "ui-monospace, SFMono-Regular, Menlo, monospace",
                            fontSize: 12,
                            background: "#f4f4f5",
                            padding: "1px 6px",
                            borderRadius: 4,
                          }}
                        >
                          {p.name}
                        </code>{" "}
                        <span style={{ color: "#71717a" }}>({p.in})</span>
                        {p.required ? (
                          <span
                            style={{ color: "#b91c1c", marginLeft: 6 }}
                          >
                            required
                          </span>
                        ) : null}
                        {p.description ? (
                          <div
                            style={{
                              color: "#52525b",
                              fontSize: 12,
                              marginTop: 2,
                            }}
                          >
                            {p.description}
                          </div>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {op.requestBody ? (
                <div style={{ marginTop: 14 }}>
                  <h3
                    style={{
                      fontSize: 11,
                      textTransform: "uppercase",
                      letterSpacing: 0.5,
                      color: "#71717a",
                      margin: "0 0 6px 0",
                    }}
                  >
                    Request body
                  </h3>
                  <p style={{ margin: 0, fontSize: 13, color: "#3f3f46" }}>
                    {op.requestBody.description ?? "JSON body"}
                    {op.requestBody.content
                      ? ` (${Object.keys(op.requestBody.content).join(", ")})`
                      : ""}
                  </p>
                </div>
              ) : null}

              {responses.length > 0 ? (
                <div style={{ marginTop: 14 }}>
                  <h3
                    style={{
                      fontSize: 11,
                      textTransform: "uppercase",
                      letterSpacing: 0.5,
                      color: "#71717a",
                      margin: "0 0 6px 0",
                    }}
                  >
                    Responses
                  </h3>
                  <ul
                    style={{
                      margin: 0,
                      padding: 0,
                      listStyle: "none",
                      fontSize: 13,
                    }}
                  >
                    {responses.map(([code, r]) => (
                      <li
                        key={code}
                        style={{ padding: "2px 0", color: "#3f3f46" }}
                      >
                        <code
                          style={{
                            fontFamily:
                              "ui-monospace, SFMono-Regular, Menlo, monospace",
                            fontSize: 12,
                            fontWeight: 600,
                          }}
                        >
                          {code}
                        </code>
                        {r.description ? (
                          <span style={{ color: "#52525b", marginLeft: 8 }}>
                            {r.description}
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </article>
          );
        })}
      </section>
    </main>
  );
}
