"use client";

import { useState } from "react";
import { RouteMap } from "@/components/map/RouteMap";
import { StatusBadge } from "@/components/StatusBadge";
import { TopNav } from "@/components/TopNav";
import { useDelivery } from "@/context/DeliveryContext";

export default function ConductorPage() {
  const { delivery, intervalMs, aceptarEntrega, rechazarEntregaConductor } = useDelivery();
  const [observaciones, setObservaciones] = useState("");

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-8">
      <TopNav />
      <header className="rounded-2xl border border-brand-100 bg-white p-6 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-brand-700">App conductor</p>
        <h1 className="mt-1 text-2xl font-bold text-slate-900">Aceptar entregas estilo indrive / rappi</h1>
      </header>

      <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="mb-4 text-lg font-bold text-slate-900">Ruta asignada</h2>
          <RouteMap route={delivery.ruta} currentPoint={delivery.puntoActual} />
          <p className="mt-4 text-sm text-slate-600">Cuando aceptas la entrega, inicia el request recurrente al backend cada {intervalMs / 1000} segundos para actualizar ubicacion.</p>
        </div>

        <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="text-lg font-bold text-slate-900">Entrega actual</h2>
          <p className="text-sm text-slate-700">Pedido: {delivery.id}</p>
          <p className="text-sm text-slate-700">Colegio: {delivery.colegio}</p>
          <p className="text-sm text-slate-700">Conductor asignado: {delivery.conductor ?? "No asignado"}</p>
          <div>
            <StatusBadge status={delivery.status} />
          </div>

          <button
            type="button"
            onClick={aceptarEntrega}
            disabled={delivery.status !== "asignado"}
            className="w-full rounded-lg bg-brand-700 px-4 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            Aceptar entrega e iniciar tracking
          </button>

          <label className="block text-sm font-medium text-slate-700">
            Observaciones
            <textarea
              value={observaciones}
              onChange={(event) => setObservaciones(event.target.value)}
              placeholder="Motivo del rechazo o novedad"
              className="mt-1 min-h-[90px] w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-brand-500"
            />
          </label>
          <button
            type="button"
            onClick={() => rechazarEntregaConductor(observaciones || "Rechazado por conductor")}
            className="w-full rounded-lg bg-rose-600 px-4 py-2 font-semibold text-white hover:bg-rose-700"
          >
            Rechazar entrega
          </button>
        </div>
      </section>
    </main>
  );
}
