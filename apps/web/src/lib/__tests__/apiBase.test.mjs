import test from "node:test";
import assert from "node:assert/strict";

import { resolveApiBase } from "../apiBase.js";

test("browser API calls use the current origin instead of hardcoded localhost", () => {
  assert.equal(resolveApiBase("http://localhost:8050/api/v1", true), "/api/v1");
});

test("server API calls retain the configured absolute backend URL", () => {
  assert.equal(resolveApiBase("http://127.0.0.1:8050/api/v1/", false), "http://127.0.0.1:8050/api/v1");
});
