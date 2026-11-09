"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { buildInitialDelivery } from "@/lib/mockRoute";
import { Delivery, DeliveryDraft } from "@/types/domain";

const STORAGE_KEY = "pae-go-delivery";
const POLL_INTERVAL_MS = 3000;

type DeliveryContextValue = {
  delivery: Delivery;
  intervalMs: number;
  registrarEnvio: (draft: DeliveryDraft) => void;
  asignarConductor: (nombre: string) => void;
  aceptarEntrega: () => void;
  rechazarEntregaConductor: (observaciones: string) => void;
  confirmarEntregaColegio: (aceptado: boolean, observaciones: string) => void;
};

const DeliveryContext = createContext<DeliveryContextValue | null>(null);

function nowIso() {
  return new Date().toISOString();
}

function updateTimestamp(delivery: Delivery): Delivery {
  return { ...delivery, actualizadoEn: nowIso() };
}

export function DeliveryProvider({ children }: { children: React.ReactNode }) {
  const [delivery, setDelivery] = useState<Delivery>(() => buildInitialDelivery());

  useEffect(() => {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      try {
        setDelivery(JSON.parse(raw) as Delivery);
      } catch {
        setDelivery(buildInitialDelivery());
      }
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(delivery));
  }, [delivery]);

  useEffect(() => {
    if (delivery.status !== "en_camino") {
      return;
    }
    const timer = window.setInterval(() => {
      setDelivery((current) => {
        if (current.status !== "en_camino") {
          return current;
        }
        const nextPoint = Math.min(current.puntoActual + 1, current.ruta.length - 1);
        if (nextPoint >= current.ruta.length - 1) {
          return updateTimestamp({
            ...current,
            puntoActual: nextPoint,
            status: "en_puerta_colegio"
          });
        }
        return updateTimestamp({
          ...current,
          puntoActual: nextPoint
        });
      });
    }, POLL_INTERVAL_MS);

    return () => window.clearInterval(timer);
  }, [delivery.status, delivery.ruta.length]);

  const value = useMemo<DeliveryContextValue>(
    () => ({
      delivery,
      intervalMs: POLL_INTERVAL_MS,
      registrarEnvio: (draft) => {
        setDelivery((current) =>
          updateTimestamp({
            ...current,
            id: `PAE-${Math.floor(Math.random() * 9000 + 1000)}`,
            colegio: draft.colegio,
            origen: draft.origen,
            destino: draft.destino,
            comidas: draft.comidas,
            conductor: null,
            status: "pendiente_asignacion",
            observaciones: "",
            puntoActual: 0
          })
        );
      },
      asignarConductor: (nombre) => {
        setDelivery((current) =>
          updateTimestamp({
            ...current,
            conductor: nombre,
            status: "asignado"
          })
        );
      },
      aceptarEntrega: () => {
        setDelivery((current) => {
          if (current.status !== "asignado") {
            return current;
          }
          return updateTimestamp({
            ...current,
            status: "en_camino"
          });
        });
      },
      rechazarEntregaConductor: (observaciones) => {
        setDelivery((current) =>
          updateTimestamp({
            ...current,
            status: "rechazado",
            observaciones
          })
        );
      },
      confirmarEntregaColegio: (aceptado, observaciones) => {
        setDelivery((current) =>
          updateTimestamp({
            ...current,
            status: aceptado ? "entregado" : "rechazado",
            observaciones
          })
        );
      }
    }),
    [delivery]
  );

  return <DeliveryContext.Provider value={value}>{children}</DeliveryContext.Provider>;
}

export function useDelivery() {
  const ctx = useContext(DeliveryContext);
  if (!ctx) {
    throw new Error("useDelivery debe usarse dentro de DeliveryProvider");
  }
  return ctx;
}
