/// <reference types="vite/client" />
import { describe, expect, it } from "vitest";

/**
 * Architecture guard: components must never call fetch() directly — all network
 * access goes through the typed API client (src/api/client.ts). This keeps the
 * network layer in one place and the components purely presentational.
 *
 * Uses Vite's import.meta.glob to read component sources as raw strings, so the
 * test needs no Node type definitions.
 */
const componentSources = import.meta.glob("./components/*.tsx", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

describe("no direct fetch in components", () => {
  it("finds component files to scan", () => {
    expect(Object.keys(componentSources).length).toBeGreaterThan(0);
  });

  it("no component file calls fetch() directly", () => {
    const offenders = Object.entries(componentSources)
      .filter(([, source]) => source.includes("fetch("))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });

  it("no component hard-codes the handoff API paths (they go through the client)", () => {
    const offenders = Object.entries(componentSources)
      .filter(([, source]) => source.includes("/api/handoff/"))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });
});
