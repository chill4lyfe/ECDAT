"use client";

import type { Finding } from "@/lib/types";

const slots = [
  { x: 378, y: 82 },
  { x: 522, y: 146 },
  { x: 454, y: 272 },
  { x: 286, y: 272 },
  { x: 218, y: 146 },
  { x: 370, y: 330 },
] as const;

function shorten(value: string, max = 18) {
  return value.length <= max ? value : `${value.slice(0, max - 1)}…`;
}

export function CryptoFlow({ findings, selectedId, onSelect }: {
  findings: Finding[];
  selectedId?: string;
  onSelect: (finding: Finding) => void;
}) {
  const visible = findings.slice(0, slots.length);
  return (
    <div className="flow-card panel">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">LIVE CRYPTOGRAPH</span>
          <h2>Discovery topology</h2>
        </div>
        <span className="live-pill"><i /> evidence-linked</span>
      </div>
      <svg className="crypto-flow" viewBox="0 0 740 390" role="img" aria-label="Cryptographic discovery topology">
        <defs>
          <radialGradient id="hubGlow">
            <stop offset="0" stopColor="rgba(117,255,214,.34)" />
            <stop offset="1" stopColor="rgba(117,255,214,0)" />
          </radialGradient>
          <filter id="softGlow"><feGaussianBlur stdDeviation="3.4" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
        </defs>
        <circle cx="370" cy="190" r="116" fill="url(#hubGlow)" opacity=".38" />
        <circle cx="370" cy="190" r="56" className="hub-ring" />
        <circle cx="370" cy="190" r="38" className="hub-core" />
        <text x="370" y="186" textAnchor="middle" className="hub-label">TARGET</text>
        <text x="370" y="204" textAnchor="middle" className="hub-sub">enterprise</text>

        {visible.map((finding, index) => {
          const slot = slots[index];
          const pathId = `edge-${finding.id}`;
          const selected = selectedId === finding.id;
          return (
            <g key={finding.id} className={selected ? "flow-node selected" : "flow-node"} onClick={() => onSelect(finding)}>
              <path id={pathId} d={`M 370 190 Q ${(370 + slot.x) / 2 + (index % 2 ? 24 : -24)} ${(190 + slot.y) / 2} ${slot.x} ${slot.y}`} className="flow-edge" />
              <circle r="3.5" className="flow-particle">
                <animateMotion dur={`${3.2 + index * .35}s`} repeatCount="indefinite"><mpath href={`#${pathId}`} /></animateMotion>
              </circle>
              <circle cx={slot.x} cy={slot.y} r="27" className="asset-orbit" />
              <circle cx={slot.x} cy={slot.y} r="6" className="asset-dot" filter="url(#softGlow)" />
              <text x={slot.x} y={slot.y + 43} textAnchor="middle" className="asset-label">{shorten(finding.asset.canonical_name)}</text>
              <text x={slot.x} y={slot.y + 57} textAnchor="middle" className="asset-type">{finding.asset.asset_type}</text>
            </g>
          );
        })}

        {visible.length === 0 && (
          <text x="370" y="322" textAnchor="middle" className="empty-flow">RUN DISCOVERY TO MATERIALIZE EVIDENCE PATHS</text>
        )}
      </svg>
    </div>
  );
}
