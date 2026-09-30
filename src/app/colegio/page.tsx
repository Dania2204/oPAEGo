"use client";

import { useState } from "react";
import { RouteMap } from "@/components/map/RouteMap";
import { StatusBadge } from "@/components/StatusBadge";
import { TopNav } from "@/components/TopNav";
import { useDelivery } from "@/context/DeliveryContext";

export default function ColegioPage() {
  const { delivery, confirmarEntregaColegio } = useDelivery();
  const [observaciones, setObservaciones] = useState("");

  const canConfirm = delivery.status === "en_puerta_colegio";

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-8">
      <TopNav />
      <header className="rounded-2xl border border-brand-100 bg-white p-6 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-brand-700">Portal colegio</p>
        <h1 className="mt-1 text-2xl font-bold text-slate-900">Recepcion de pedidos PAE con observaciones</h1>
      </header>

      <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="mb-4 text-lg font-bold text-slate-900">Seguimiento del conductor</h2>
          <RouteMap route={delivery.ruta} currentPoint={delivery.puntoActual} />
        </div>

        <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="text-lg font-bold text-slate-900">Estado del pedido</h2>
          <p className="text-sm text-slate-700">Pedido: {delivery.id}</p>
          <p className="text-sm text-slate-700">Origen: {delivery.origen}</p>
          <p className="text-sm text-slate-700">Destino: {delivery.destino}</p>
          <p className="text-sm text-slate-700">Comidas: {delivery.comidas}</p>
          <div>
            <StatusBadge status={delivery.status} />
          </div>

          <label className="block text-sm font-medium text-slate-700">
            Observaciones de recibo
            <textarea
              value={observaciones}
              onChange={(event) => setObservaciones(event.target.value)}
              placeholder="Ej: faltaron bandejas o temperatura inadecuada"
              className="mt-1 min-h-[90px] w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-brand-500"
            />
          </label>

          <div className="grid gap-3 sm:grid-cols-2">
            <button
              type="button"
              disabled={!canConfirm}
              onClick={() => confirmarEntregaColegio(true, observaciones || "Recibido conforme")}
              className="rounded-lg bg-emerald-600 px-4 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              Aceptar pedido
            </button>
            <button
              type="button"
              disabled={!canConfirm}
              onClick={() => confirmarEntregaColegio(false, observaciones || "Pedido rechazado por colegio")}
              className="rounded-lg bg-rose-600 px-4 py-2 font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              Rechazar pedido
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
