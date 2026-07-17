"use client";

import { ApiKeyModal } from "@/components/ApiKeyModal";
import { setOnApiKeyRequired } from "@/lib/api";
import { useEffect, useState } from "react";

/** Client shell that mounts the first-visit API key modal. */
export function ApiKeyGate({ children }: { children: React.ReactNode }) {
  const [force, setForce] = useState(false);

  useEffect(() => {
    setOnApiKeyRequired(() => setForce(true));
    const onNeed = () => setForce(true);
    window.addEventListener("jessie:api-key-required", onNeed);
    return () => window.removeEventListener("jessie:api-key-required", onNeed);
  }, []);

  return (
    <>
      <ApiKeyModal forceOpen={force} />
      {children}
    </>
  );
}
