import { Suspense } from "react";
import { ReportsClient } from "@/components/reports/ReportsClient";
export default function ReportsPage() { return <Suspense fallback={<div style={{padding:40}}>Preparing report…</div>}><ReportsClient /></Suspense>; }
