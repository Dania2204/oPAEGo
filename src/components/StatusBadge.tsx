import { DeliveryStatus } from "@/types/domain";

const statusStyles: Record<DeliveryStatus, string> = {
  pendiente_asignacion: "bg-slate-100 text-slate-700",
  asignado: "bg-blue-100 text-blue-700",
  en_camino: "bg-amber-100 text-amber-800",
  en_puerta_colegio: "bg-orange-100 text-orange-800",
  entregado: "bg-emerald-100 text-emerald-800",
  rechazado: "bg-rose-100 text-rose-700"
};

const statusLabels: Record<DeliveryStatus, string> = {
  pendiente_asignacion: "Pendiente asignacion",
  asignado: "Asignado",
  en_camino: "En camino",
  en_puerta_colegio: "En puerta del colegio",
  entregado: "Entregado",
  rechazado: "Rechazado"
};

export function StatusBadge({ status }: { status: DeliveryStatus }) {
  return (
    <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${statusStyles[status]}`}>
      {statusLabels[status]}
    </span>
  );
}
