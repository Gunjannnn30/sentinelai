import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Auto-cleanup only activates when test globals are enabled; we keep globals
// off, so unmount + clear the DOM between tests explicitly.
afterEach(() => {
  cleanup();
});
