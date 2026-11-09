"use client";

import { DeliveryProvider } from "@/context/DeliveryContext";

export function AppProviders({ children }: { children: React.ReactNode }) {
  return <DeliveryProvider>{children}</DeliveryProvider>;
}
