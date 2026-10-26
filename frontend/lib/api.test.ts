import { describe, expect, it } from "vitest";
import { csrfHeaders, readCookie, qs, apiErrorFromBody, ApiError } from "./api";

describe("readCookie", () => {
  it("reads a named cookie from a cookie string", () => {
    expect(readCookie("sentinel_csrf", "a=1; sentinel_csrf=abc123; b=2")).toBe("abc123");
  });

  it("returns null when the cookie is absent", () => {
    expect(readCookie("sentinel_csrf", "a=1; b=2")).toBeNull();
  });

  it("does not match a cookie whose name merely starts with the needle", () => {
    expect(readCookie("csrf", "sentinel_csrf=abc")).toBeNull();
  });
});

describe("csrfHeaders", () => {
  it("sends X-CSRF-Token on unsafe methods when the cookie exists", () => {
    expect(csrfHeaders("POST", "token-123")).toEqual({ "X-CSRF-Token": "token-123" });
    expect(csrfHeaders("PUT", "token-123")).toEqual({ "X-CSRF-Token": "token-123" });
    expect(csrfHeaders("PATCH", "token-123")).toEqual({ "X-CSRF-Token": "token-123" });
    expect(csrfHeaders("DELETE", "token-123")).toEqual({ "X-CSRF-Token": "token-123" });
  });

  it("never sends the header on GET", () => {
    expect(csrfHeaders("GET", "token-123")).toEqual({});
  });

  it("omits the header when no cookie is present", () => {
    expect(csrfHeaders("POST", null)).toEqual({});
  });
});

describe("qs", () => {
  it("drops empty values and encodes the rest", () => {
    expect(qs({ a: 1, b: "", c: null, d: "x y" })).toBe("?a=1&d=x+y");
  });

  it("returns an empty string when nothing survives", () => {
    expect(qs({ a: undefined, b: "" })).toBe("");
  });
});

describe("apiErrorFromBody", () => {
  it("maps the backend error envelope", () => {
    const err = apiErrorFromBody(403, {
      error: { code: "csrf_failed", message: "CSRF validation failed.", request_id: "req-9" },
    });
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(403);
    expect(err.code).toBe("csrf_failed");
    expect(err.message).toBe("CSRF validation failed.");
    expect(err.requestId).toBe("req-9");
  });

  it("falls back to a generic message for non-envelope bodies", () => {
    const err = apiErrorFromBody(500, null);
    expect(err.code).toBe("http_500");
    expect(err.message).toContain("500");
  });
});
