import { redirect } from "next/navigation";
import { getLegacyWorkspaceRedirect } from "@/lib/productFocus";

export default function BrandKitRedirectPage() {
  redirect(getLegacyWorkspaceRedirect("/brand-kit")!);
}
