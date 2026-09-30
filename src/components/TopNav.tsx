"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

const links = [
  { href: "/", label: "Inicio" },
  { href: "/alcaldia", label: "Alcaldia" },
  { href: "/conductor", label: "Conductor" },
  { href: "/colegio", label: "Colegio" }
];

export function TopNav() {
  const router = useRouter();

  const logout = async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/");
    router.refresh();
  };

  return (
    <nav className="flex flex-wrap items-center gap-2">
      {links.map((link) => (
        <Link
          key={link.href}
          href={link.href}
          className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:border-brand-500 hover:text-brand-700"
        >
          {link.label}
        </Link>
      ))}
      <button
        type="button"
        onClick={logout}
        className="rounded-full border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700 hover:border-rose-500"
      >
        Cerrar sesion
      </button>
    </nav>
  );
}
