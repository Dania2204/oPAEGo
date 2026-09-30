"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

export function LoginForm() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password })
      });

      const payload = (await response.json()) as { message?: string; nextPath?: string };
      if (!response.ok) {
        setError(payload.message ?? "No se pudo iniciar sesion.");
        return;
      }

      router.push(payload.nextPath ?? "/");
      router.refresh();
    } catch {
      setError("Error de red en el login.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="w-full space-y-4 rounded-2xl border border-slate-300 bg-white/90 p-6 shadow-lg">
      <div>
        <label className="mb-1 block text-sm font-semibold text-slate-700">Correo</label>
        <input
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          type="email"
          autoComplete="username"
          required
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 outline-none focus:border-brand-700"
        />
      </div>

      <div>
        <label className="mb-1 block text-sm font-semibold text-slate-700">Contrasena</label>
        <input
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          type="password"
          autoComplete="current-password"
          required
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-slate-900 outline-none focus:border-brand-700"
        />
      </div>

      {error ? <p className="text-sm font-medium text-rose-700">{error}</p> : null}

      <button type="submit" disabled={loading} className="w-full rounded-lg bg-brand-700 px-4 py-2 font-semibold text-white hover:bg-brand-900 disabled:opacity-60">
        {loading ? "Ingresando..." : "Iniciar sesion"}
      </button>
    </form>
  );
}
