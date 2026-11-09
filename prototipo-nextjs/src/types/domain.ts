export type Role = "alcaldia" | "conductor" | "colegio";

export type DeliveryStatus =
  | "pendiente_asignacion"
  | "asignado"
  | "en_camino"
  | "en_puerta_colegio"
  | "entregado"
  | "rechazado";

export type LatLngPoint = {
  lat: number;
  lng: number;
};

export type Delivery = {
  id: string;
  colegio: string;
  origen: string;
  destino: string;
  comidas: number;
  conductor: string | null;
  status: DeliveryStatus;
  observaciones: string;
  ruta: LatLngPoint[];
  puntoActual: number;
  actualizadoEn: string;
};

export type DeliveryDraft = {
  colegio: string;
  origen: string;
  destino: string;
  comidas: number;
};
