"use client";

import { FormEvent, useState } from "react";
import { RouteMap } from "@/components/map/RouteMap";
import { StatusBadge } from "@/components/StatusBadge";
import { TopNav } from "@/components/TopNav";
import { useDelivery } from "@/context/DeliveryContext";

export default function AlcaldiaPage() {
  const { delivery, intervalMs, registrarEnvio, asignarConductor } = useDelivery();
  const [colegio, setColegio] = useState(delivery.colegio);
  const [origen, setOrigen] = useState(delivery.origen);
  const [destino, setDestino] = useState(delivery.destino);
  const [comidas, setComidas] = useState<number>(delivery.comidas);
  const [conductor, setConductor] = useState(delivery.conductor ?? "Juan Perez");

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    registrarEnvio({ colegio, origen, destino, comidas });
  };

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-8">
      <TopNav />
      <header className="rounded-2xl border border-brand-100 bg-white p-6 shadow-sm">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-brand-700">Panel de alcaldia</p>
        <h1 className="mt-1 text-2xl font-bold text-slate-900">Registro de comidas, envios y conductores</h1>
      </header>

      <section className="grid gap-6 lg:grid-cols-2">
        <form onSubmit={onSubmit} className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="text-lg font-bold text-slate-900">Registrar envio</h2>
          <label className="block text-sm font-medium text-slate-700">
            Colegio
            <input value={colegio} onChange={(e) => setColegio(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-brand-500" />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Origen
            <input value={origen} onChange={(e) => setOrigen(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-brand-500" />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Destino
            <input value={destino} onChange={(e) => setDestino(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-brand-500" />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Cantidad de comidas
            <input
              type="number"
              min={1}
              value={comidas}
              onChange={(e) => setComidas(Number(e.target.value))}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-brand-500"
            />
          </label>
          <button type="submit" className="w-full rounded-lg bg-brand-700 px-4 py-2 font-semibold text-white hover:bg-brand-900">
            Guardar envio
          </button>
        </form>

        <div className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6">
          <h2 className="text-lg font-bold text-slate-900">Asignar conductor</h2>
          <label className="block text-sm font-medium text-slate-700">
            Nombre del conductor
            <input value={conductor} onChange={(e) => setConductor(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 outline-none focus:border-brand-500" />
          </label>
          <button type="button" onClick={() => asignarConductor(conductor)} className="rounded-lg bg-slate-900 px-4 py-2 font-semibold text-white hover:bg-slate-700">
            Asignar al envio actual
          </button>

          <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-700">
            <p>
              Estado: <StatusBadge status={delivery.status} />
            </p>
            <p className="mt-2">Pedido: {delivery.id}</p>
            <p>Colegio: {delivery.colegio}</p>
            <p>Conductor: {delivery.conductor ?? "Sin asignar"}</p>
            <p>Polling conductor-backend: cada {intervalMs / 1000} segundos</p>
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="mb-4 text-lg font-bold text-slate-900">Monitoreo de ruta en tiempo real</h2>
        <RouteMap route={delivery.ruta} currentPoint={delivery.puntoActual} />
      </section>
    </main>
  );
}
