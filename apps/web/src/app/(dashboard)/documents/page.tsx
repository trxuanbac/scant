import { redirect } from "next/navigation";
import { getLegacyWorkspaceRedirect } from "@/lib/productFocus";

export default function DocumentsRedirectPage() {
  redirect(getLegacyWorkspaceRedirect("/documents")!);
}
