import { Suspense } from "react";
import { InvestigationClient } from "@/components/investigate/InvestigationClient";

export default function InvestigationPage() {
  return <Suspense fallback={<div style={{padding:40}}>Loading assessment…</div>}><InvestigationClient /></Suspense>;
}
