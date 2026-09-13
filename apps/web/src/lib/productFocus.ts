export type WorkspaceRouteKey =
  | "home"
  | "new"
  | "projects"
  | "data"
  | "research"
  | "templates"
  | "settings"
  | "admin";

export interface WorkspaceRoute {
  key: WorkspaceRouteKey;
  href: string;
}

const CORE_WORKSPACE_NAVIGATION: readonly WorkspaceRoute[] = [
  { key: "home", href: "/" },
  { key: "new", href: "/projects/new" },
  { key: "projects", href: "/projects" },
  { key: "data", href: "/data" },
  { key: "research", href: "/research" },
  { key: "templates", href: "/templates" },
  { key: "settings", href: "/settings" },
];

export function getWorkspaceNavigation(isAdmin: boolean): WorkspaceRoute[] {
  const routes = CORE_WORKSPACE_NAVIGATION.map((route) => ({ ...route }));
  if (isAdmin) routes.push({ key: "admin", href: "/admin" });
  return routes;
}

export function getVisibleProjectTypes(): string[] {
  return ["business_report", "data_analysis", "research", "custom"];
}

export function normalizeNewProjectType(projectType: string | null | undefined): string {
  if (projectType === "business_report" || projectType === "data_analysis" || projectType === "research") {
    return projectType;
  }
  if (projectType === "technical" || projectType === "financial" || projectType === "proposal") {
    return "business_report";
  }
  if (projectType === "market_research") return "research";
  return "custom";
}

const LEGACY_WORKSPACE_REDIRECTS: Readonly<Record<string, string>> = {
  "/documents": "/projects?view=reports",
  "/sources": "/research?view=library",
  "/brand-kit": "/settings?tab=brand",
};

export function getLegacyWorkspaceRedirect(pathname: string): string | null {
  return LEGACY_WORKSPACE_REDIRECTS[pathname] ?? null;
}
