/**
 * Tests for VoyagentApiError — the one exception callers are supposed to
 * match on with `instanceof`. Keeping the shape locked down here so
 * consumers can rely on it.
 */
import { describe, expect, it } from "vitest";

import { VoyagentApiError } from "../src/errors.js";

describe("VoyagentApiError", () => {
  it("is an Error subclass with name=VoyagentApiError", () => {
    const err = new VoyagentApiError({
      status: 500,
      method: "GET",
      path: "/x",
      responseBodyPreview: "oops",
    });
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("VoyagentApiError");
  });

  it("builds a readable default message including status / method / path / body", () => {
    const err = new VoyagentApiError({
      status: 418,
      method: "POST",
      path: "/teapot",
      responseBodyPreview: "I am a teapot",
    });
    expect(err.message).toContain("POST");
    expect(err.message).toContain("/teapot");
    expect(err.message).toContain("418");
    expect(err.message).toContain("I am a teapot");
  });

  it("preserves explicit message override", () => {
    const err = new VoyagentApiError({
      status: 401,
      method: "GET",
      path: "/x",
      responseBodyPreview: "",
      message: "token expired",
    });
    expect(err.message).toBe("token expired");
  });

  it("stores all fields as readonly properties", () => {
    const err = new VoyagentApiError({
      status: 404,
      method: "DELETE",
      path: "/a/b",
      responseBodyPreview: "nope",
    });
    expect(err.status).toBe(404);
    expect(err.method).toBe("DELETE");
    expect(err.path).toBe("/a/b");
    expect(err.responseBodyPreview).toBe("nope");
  });
});
