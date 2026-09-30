"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { MapContainer, Marker, Polyline, Popup, TileLayer } from "react-leaflet";
import { LatLngPoint } from "@/types/domain";

delete (L.Icon.Default.prototype as unknown as { _getIconUrl?: unknown })._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png"
});

const endIcon = new L.Icon({
  iconUrl: "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-red.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41]
});

const driverIcon = new L.Icon({
  iconUrl: "https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-green.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41]
});

type Props = {
  route: LatLngPoint[];
  currentPoint: number;
};

export default function RouteMapClient({ route, currentPoint }: Props) {
  const center = route[Math.max(0, Math.min(currentPoint, route.length - 1))] ?? { lat: 4.648625, lng: -74.102911 };
  const current = route[currentPoint] ?? route[0];

  return (
    <div className="h-[420px] w-full overflow-hidden rounded-2xl border border-slate-200">
      <MapContainer center={center} zoom={14} scrollWheelZoom className="h-full w-full">
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />

        <Polyline positions={route} pathOptions={{ color: "#2f7d32", weight: 5 }} />

        {route[0] ? (
          <Marker position={route[0]}>
            <Popup>Origen PAE</Popup>
          </Marker>
        ) : null}

        {route[route.length - 1] ? (
          <Marker position={route[route.length - 1]} icon={endIcon}>
            <Popup>Colegio destino</Popup>
          </Marker>
        ) : null}

        {current ? (
          <Marker position={current} icon={driverIcon}>
            <Popup>Conductor en ruta</Popup>
          </Marker>
        ) : null}
      </MapContainer>
    </div>
  );
}
