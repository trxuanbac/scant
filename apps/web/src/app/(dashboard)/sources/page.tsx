import { redirect } from "next/navigation";
import { getLegacyWorkspaceRedirect } from "@/lib/productFocus";

export default function SourcesRedirectPage() {
  redirect(getLegacyWorkspaceRedirect("/sources")!);
}
