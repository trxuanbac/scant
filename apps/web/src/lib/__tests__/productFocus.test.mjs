import test from "node:test";
import assert from "node:assert/strict";

import {
  getLegacyWorkspaceRedirect,
  normalizeNewProjectType,
  getVisibleProjectTypes,
  getWorkspaceNavigation,
} from "../productFocus.ts";

test("focused workspace navigation keeps seven core destinations for regular users", () => {
  assert.deepEqual(
    getWorkspaceNavigation(false).map(({ key, href }) => ({ key, href })),
    [
      { key: "home", href: "/" },
      { key: "new", href: "/projects/new" },
      { key: "projects", href: "/projects" },
      { key: "data", href: "/data" },
      { key: "research", href: "/research" },
      { key: "templates", href: "/templates" },
      { key: "settings", href: "/settings" },
    ],
  );
});

test("focused workspace navigation exposes admin only to administrators", () => {
  assert.equal(getWorkspaceNavigation(false).some(({ key }) => key === "admin"), false);
  assert.deepEqual(getWorkspaceNavigation(true).at(-1), { key: "admin", href: "/admin" });
});

test("new projects expose four focused workflows", () => {
  assert.deepEqual(getVisibleProjectTypes(), [
    "business_report",
    "data_analysis",
    "research",
    "custom",
  ]);
});

test("legacy creation types resolve to a focused workflow", () => {
  assert.equal(normalizeNewProjectType("technical"), "business_report");
  assert.equal(normalizeNewProjectType("financial"), "business_report");
  assert.equal(normalizeNewProjectType("proposal"), "business_report");
  assert.equal(normalizeNewProjectType("market_research"), "research");
  assert.equal(normalizeNewProjectType("data_analysis"), "data_analysis");
  assert.equal(normalizeNewProjectType("unknown"), "custom");
});

test("legacy workspace routes resolve to focused destinations", () => {
  assert.equal(getLegacyWorkspaceRedirect("/documents"), "/projects?view=reports");
  assert.equal(getLegacyWorkspaceRedirect("/sources"), "/research?view=library");
  assert.equal(getLegacyWorkspaceRedirect("/brand-kit"), "/settings?tab=brand");
  assert.equal(getLegacyWorkspaceRedirect("/projects"), null);
});
