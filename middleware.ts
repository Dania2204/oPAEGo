import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const ROLE_BY_PREFIX: Record<string, string> = {
  "/alcaldia": "ADMIN",
  "/conductor": "DRIVER",
  "/colegio": "USER"
};

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  if (pathname.startsWith("/api") || pathname.startsWith("/_next") || pathname.includes(".")) {
    return NextResponse.next();
  }

  const session = request.cookies.get("pae_session")?.value;
  const role = request.cookies.get("pae_role")?.value;

  if (pathname === "/") {
    if (session && role) {
      const target = role === "ADMIN" ? "/alcaldia" : role === "DRIVER" ? "/conductor" : "/colegio";
      return NextResponse.redirect(new URL(target, request.url));
    }
    return NextResponse.next();
  }

  const expectedRole = Object.entries(ROLE_BY_PREFIX).find(([prefix]) => pathname.startsWith(prefix))?.[1];
  if (!expectedRole) {
    return NextResponse.next();
  }

  if (!session || role !== expectedRole) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!favicon.ico).*)"]
};
