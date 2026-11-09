"use client";

import dynamic from "next/dynamic";
import { LatLngPoint } from "@/types/domain";

const RouteMapClient = dynamic(() => import("@/components/map/RouteMapClient"), {
  ssr: false
});

type Props = {
  route: LatLngPoint[];
  currentPoint: number;
};

export function RouteMap(props: Props) {
  return <RouteMapClient {...props} />;
}
