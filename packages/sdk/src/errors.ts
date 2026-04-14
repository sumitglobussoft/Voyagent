/**
 * Typed error thrown by the Voyagent SDK on non-2xx responses.
 *
 * Kept intentionally shallow — one class, plain fields. Callers can
 * `instanceof VoyagentApiError` and read status / method / path / body preview
 * without reaching into a cause chain.
 */
export class VoyagentApiError extends Error {
  readonly status: number;
  readonly method: string;
  readonly path: string;
  readonly responseBodyPreview: string;

  constructor(args: {
    status: number;
    method: string;
    path: string;
    responseBodyPreview: string;
    message?: string;
  }) {
    const msg =
      args.message ??
      `Voyagent API ${args.method} ${args.path} failed with ${args.status}: ${args.responseBodyPreview}`;
    super(msg);
    this.name = "VoyagentApiError";
    this.status = args.status;
    this.method = args.method;
    this.path = args.path;
    this.responseBodyPreview = args.responseBodyPreview;
  }
}
