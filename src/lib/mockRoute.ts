import { Delivery, DeliveryDraft, LatLngPoint } from "@/types/domain";

const routePoints: LatLngPoint[] = [
  { lat: 4.648625, lng: -74.102911 },
  { lat: 4.64915, lng: -74.10035 },
  { lat: 4.6498, lng: -74.0975 },
  { lat: 4.65015, lng: -74.0949 },
  { lat: 4.65055, lng: -74.0926 },
  { lat: 4.65115, lng: -74.0902 },
  { lat: 4.6518, lng: -74.0879 },
  { lat: 4.6524, lng: -74.08575 },
  { lat: 4.6531, lng: -74.0837 },
  { lat: 4.65375, lng: -74.08195 },
  { lat: 4.6544, lng: -74.08045 }
];

const defaultDraft: DeliveryDraft = {
  colegio: "Colegio Distrital San Gabriel",
  origen: "Bodega PAE Kennedy",
  destino: "Colegio Distrital San Gabriel",
  comidas: 320
};

export function buildInitialDelivery(): Delivery {
  return {
    id: `PAE-${Math.floor(Math.random() * 9000 + 1000)}`,
    colegio: defaultDraft.colegio,
    origen: defaultDraft.origen,
    destino: defaultDraft.destino,
    comidas: defaultDraft.comidas,
    conductor: null,
    status: "pendiente_asignacion",
    observaciones: "",
    ruta: routePoints,
    puntoActual: 0,
    actualizadoEn: new Date().toISOString()
  };
}
