import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const token = request.cookies.get("auth_token")?.value;

  const isPublicApi = pathname.startsWith("/api/auth") || pathname.startsWith("/auth/callback");

  // Protected paths that require authentication
  const isProtectedPath =
    pathname.startsWith("/projects") ||
    pathname.startsWith("/documents") ||
    pathname.startsWith("/templates") ||
    pathname.startsWith("/data") ||
    pathname.startsWith("/research") ||
    pathname.startsWith("/brand-kit") ||
    pathname.startsWith("/settings") ||
    pathname.startsWith("/admin") ||
    pathname.startsWith("/reports");

  // If accessing protected path without token, redirect to login with callback URL
  if (isProtectedPath && !token && !isPublicApi) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except for the ones starting with:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public assets
     */
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
