# IMPLEMENTATION CONTRACT — Analyst AI (Stretch / Post-Core)

Do not implement until graph/inventory/risk retrieval is stable.

Rules:
- AI retrieves verified ECDAT data and cites finding/evidence IDs internally.
- AI may explain/correlate/rephrase; it must not invent enterprise findings.
- Deterministic scanners remain the evidence source for critical findings.
- Responses must distinguish platform facts from generated recommendations/inference.
- Natural-language queries should compile to constrained platform queries/tool calls, not direct unrestricted database prompting.
