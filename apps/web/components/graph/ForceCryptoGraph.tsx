"use client";

import * as d3 from "d3";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { GraphEdge, GraphInsight, GraphNode, RiskAssessment } from "@/lib/types";

type SimNode = GraphNode & d3.SimulationNodeDatum;
type SimLink = d3.SimulationLinkDatum<SimNode> & GraphEdge;

function riskForNode(node: GraphNode, riskByAsset: Map<string, RiskAssessment>) {
  if (!node.id.startsWith("asset:")) return undefined;
  return riskByAsset.get(node.id.slice("asset:".length));
}

function nodeRadius(node: GraphNode, insight: GraphInsight | undefined, risk: RiskAssessment | undefined, dense: boolean) {
  const centrality = Math.min(1, Math.max(0, insight?.centrality ?? 0));
  if (node.node_type === "service" || node.node_type === "application") return (dense ? 13 : 14) + centrality * 7;
  if (dense) {
    if (node.node_type === "data_class") return 7;
    if (node.node_type === "repository" || node.node_type === "container") return 7.5;
    if (node.properties.technical_component === true) return 5.5;
    return risk ? 5.4 : 4.8;
  }
  const base = node.node_type === "data_class" ? 9 : node.node_type === "repository" || node.node_type === "container" ? 8.5 : 7;
  return base + Math.min(8, centrality * 8);
}

function seededPosition(id: string, index: number, count: number, width: number, height: number) {
  let hash = 2166136261;
  for (let i = 0; i < id.length; i += 1) hash = Math.imul(hash ^ id.charCodeAt(i), 16777619);
  const jitter = ((hash >>> 0) % 997) / 997;
  const angle = (index / Math.max(1, count)) * Math.PI * 2 + jitter * .35;
  const ring = Math.min(width, height) * (.18 + (index % 4) * .035);
  return { x: width / 2 + Math.cos(angle) * ring, y: height / 2 + Math.sin(angle) * ring };
}

function endpointId(value: string | number | SimNode): string {
  return typeof value === "object" ? value.id : String(value);
}

export function ForceCryptoGraph({
  nodes,
  edges,
  risks,
  insights,
  selectedId,
  onSelect,
  compact = false,
  expanded = false,
  resetToken = 0,
  labelMode = "selection",
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  risks: RiskAssessment[];
  insights: GraphInsight[];
  selectedId?: string | null;
  onSelect?: (node: GraphNode) => void;
  compact?: boolean;
  expanded?: boolean;
  resetToken?: number;
  labelMode?: "selection" | "focus";
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const onSelectRef = useRef(onSelect);
  const [viewport, setViewport] = useState(() => ({ width: compact ? 760 : 1180, height: compact ? 405 : 700 }));
  const dense = nodes.length > (compact ? 70 : 140) || edges.length > (compact ? 180 : 340);

  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);

  useLayoutEffect(() => {
    const element = svgRef.current;
    if (!element) return;
    const update = () => {
      const rect = element.getBoundingClientRect();
      const width = Math.max(compact ? 520 : 720, Math.round(rect.width));
      const height = Math.max(expanded ? 620 : compact ? 340 : 560, Math.round(rect.height));
      setViewport((current) => Math.abs(current.width - width) < 4 && Math.abs(current.height - height) < 4 ? current : { width, height });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [compact, expanded]);

  useEffect(() => {
    const svgElement = svgRef.current;
    if (!svgElement || nodes.length === 0) return;

    const { width, height } = viewport;
    const suffix = `${compact ? "c" : expanded ? "x" : "f"}-${resetToken}`;
    const svg = d3.select(svgElement);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const defs = svg.append("defs");
    if (!dense) {
      const glow = defs.append("filter").attr("id", `node-glow-${suffix}`).attr("x", "-80%").attr("y", "-80%").attr("width", "260%").attr("height", "260%");
      glow.append("feGaussianBlur").attr("stdDeviation", compact ? 2.2 : 3.1).attr("result", "blur");
      const merge = glow.append("feMerge");
      merge.append("feMergeNode").attr("in", "blur");
      merge.append("feMergeNode").attr("in", "SourceGraphic");
      defs.append("marker")
        .attr("id", `arrow-${suffix}`)
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 18)
        .attr("refY", 0)
        .attr("markerWidth", 4)
        .attr("markerHeight", 4)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-5L10,0L0,5")
        .attr("fill", "rgba(135,154,172,.42)");
    }

    const root = svg.append("g").attr("class", `force-root${dense ? " dense-root" : ""}`);
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([dense ? .22 : .35, expanded ? 5 : 3.6])
      .on("zoom", (event) => {
        root.attr("transform", event.transform);
      });
    svg.call(zoom);
    svg.call(zoom.transform, d3.zoomIdentity);

    const riskByAsset = new Map(risks.map((risk) => [risk.asset_id, risk]));
    const insightByNode = new Map(insights.map((insight) => [insight.node_id, insight]));
    const simNodes: SimNode[] = nodes.map((node, index) => ({ ...node, ...seededPosition(node.id, index, nodes.length, width, height) }));
    const nodeIds = new Set(nodes.map((node) => node.id));
    const simLinks: SimLink[] = edges
      .filter((edge) => nodeIds.has(edge.source_id) && nodeIds.has(edge.target_id))
      .map((edge) => ({ ...edge, source: edge.source_id, target: edge.target_id }));

    const linkLayer = root.append("g").attr("class", `force-links${dense ? " dense-links" : ""}`);
    const denseLinks = dense
      ? linkLayer.selectAll<SVGLineElement, SimLink>("line").data(simLinks).join("line")
        .attr("class", (item) => `force-link dense-link edge-${item.edge_type}`)
        .attr("data-edge-id", (item) => item.id)
      : null;
    const richLinks = dense ? null : linkLayer.selectAll<SVGPathElement, SimLink>("path").data(simLinks).join("path")
      .attr("class", (item) => `force-link edge-${item.edge_type}`)
      .attr("data-edge-id", (item) => item.id)
      .attr("marker-end", `url(#arrow-${suffix})`);

    const node = root.append("g").attr("class", "force-nodes")
      .selectAll<SVGGElement, SimNode>("g")
      .data(simNodes)
      .join("g")
      .attr("data-node-id", (item) => item.id)
      .attr("class", (item) => {
        const risk = riskForNode(item, riskByAsset);
        const blocker = insightByNode.get(item.id)?.migration_blocker ? " blocker" : "";
        return `force-node type-${item.node_type}${risk ? ` risk-${risk.priority}` : ""}${dense ? " dense-node" : ""}${blocker}`;
      })
      .style("cursor", onSelectRef.current ? "pointer" : "grab")
      .on("click", (event, item) => {
        event.stopPropagation();
        onSelectRef.current?.(nodes.find((candidate) => candidate.id === item.id) ?? item);
      });

    node.filter((item) => insightByNode.get(item.id)?.migration_blocker === true)
      .append("circle")
      .attr("class", "blocker-ring")
      .attr("r", (item) => nodeRadius(item, insightByNode.get(item.id), riskForNode(item, riskByAsset), dense) + (dense ? 5 : 10));

    if (!dense) {
      node.filter((item) => Boolean(riskForNode(item, riskByAsset)))
        .append("circle")
        .attr("class", (item) => {
          const risk = riskForNode(item, riskByAsset);
          return `node-risk-ring priority-${risk?.priority ?? "unknown"}`;
        })
        .attr("r", (item) => nodeRadius(item, insightByNode.get(item.id), riskForNode(item, riskByAsset), dense) + 4.5);
    }

    node.append("circle")
      .attr("class", "node-disc")
      .attr("r", (item) => nodeRadius(item, insightByNode.get(item.id), riskForNode(item, riskByAsset), dense))
      .attr("filter", dense ? null : `url(#node-glow-${suffix})`);

    node.append("circle")
      .attr("class", "node-core")
      .attr("r", (item) => dense ? Math.max(1.4, nodeRadius(item, insightByNode.get(item.id), riskForNode(item, riskByAsset), dense) * .24) : Math.max(2.8, nodeRadius(item, insightByNode.get(item.id), riskForNode(item, riskByAsset), dense) * .28));

    // Small estates keep the rich always-labelled presentation. Dense estates retain
    // every node but keep labels dormant until an explicit node selection/search asks
    // for them. This prevents zooming from turning a large estate into a text cloud.
    if (!compact || !dense) {
      node.append("text")
        .attr("class", `force-label${dense ? " dense-context-label" : ""}`)
        .attr("text-anchor", "middle")
        .attr("x", 0)
        .attr("y", (item) => nodeRadius(item, insightByNode.get(item.id), riskForNode(item, riskByAsset), dense) + (dense ? 13 : 15))
        .text((item) => item.label.length > (dense ? 30 : 24) ? `${item.label.slice(0, dense ? 29 : 23)}…` : item.label);
      if (!dense) {
        node.append("text")
          .attr("class", "force-type")
          .attr("text-anchor", "middle")
          .attr("dy", (item) => nodeRadius(item, insightByNode.get(item.id), riskForNode(item, riskByAsset), dense) + 29)
          .text((item) => item.node_type.replaceAll("_", " "));
      }
    }

    const simulation = d3.forceSimulation<SimNode>(simNodes)
      .alpha(dense ? .72 : .9)
      .alphaDecay(dense ? .085 : .045)
      .velocityDecay(dense ? .5 : .42)
      .force("link", d3.forceLink<SimNode, SimLink>(simLinks).id((item) => item.id).distance((item) => {
        if (item.edge_type === "contains") return dense ? 42 : compact ? 60 : 98;
        if (item.edge_type === "uses") return dense ? 54 : compact ? 66 : 112;
        if (item.edge_type === "protects") return dense ? 66 : compact ? 76 : 132;
        return dense ? 76 : compact ? 92 : 154;
      }).strength(dense ? .22 : compact ? .5 : .4))
      .force("charge", d3.forceManyBody().strength(dense ? -110 : compact ? -300 : -650))
      .force("collision", d3.forceCollide<SimNode>().radius((item) => nodeRadius(item, insightByNode.get(item.id), riskForNode(item, riskByAsset), dense) + (dense ? 5 : compact ? 14 : 28)).strength(.85))
      .force("x", d3.forceX(width / 2).strength(dense ? .05 : compact ? .035 : .026))
      .force("y", d3.forceY(height / 2).strength(dense ? .055 : compact ? .04 : .028))
      .force("center", d3.forceCenter(width / 2, height / 2));

    const renderTick = () => {
      if (denseLinks) {
        denseLinks
          .attr("x1", (item) => (item.source as SimNode).x ?? 0)
          .attr("y1", (item) => (item.source as SimNode).y ?? 0)
          .attr("x2", (item) => (item.target as SimNode).x ?? 0)
          .attr("y2", (item) => (item.target as SimNode).y ?? 0);
      }
      if (richLinks) {
        richLinks.attr("d", (item) => {
          const source = item.source as SimNode;
          const target = item.target as SimNode;
          const sx = source.x ?? 0;
          const sy = source.y ?? 0;
          const tx = target.x ?? 0;
          const ty = target.y ?? 0;
          const mx = (sx + tx) / 2;
          const my = (sy + ty) / 2 - Math.min(24, Math.abs(tx - sx) * .045);
          return `M${sx},${sy} Q${mx},${my} ${tx},${ty}`;
        });
      }
      node.attr("transform", (item) => `translate(${item.x ?? 0},${item.y ?? 0})`);
    };

    // Pre-settle the complete graph once. Dense estates stay idle afterwards; dragging
    // restarts the same simulation so neighboring nodes still react naturally.
    simulation.stop();
    simulation.tick(dense ? 72 : compact ? 90 : 120);
    renderTick();

    if (simNodes.length > 1) {
      const labelAllowance = dense ? 18 : compact ? 8 : 34;
      const minX = Math.min(...simNodes.map((item) => (item.x ?? width / 2) - nodeRadius(item, insightByNode.get(item.id), riskForNode(item, riskByAsset), dense) - 12));
      const maxX = Math.max(...simNodes.map((item) => (item.x ?? width / 2) + nodeRadius(item, insightByNode.get(item.id), riskForNode(item, riskByAsset), dense) + 12));
      const minY = Math.min(...simNodes.map((item) => (item.y ?? height / 2) - nodeRadius(item, insightByNode.get(item.id), riskForNode(item, riskByAsset), dense) - 12));
      const maxY = Math.max(...simNodes.map((item) => (item.y ?? height / 2) + nodeRadius(item, insightByNode.get(item.id), riskForNode(item, riskByAsset), dense) + labelAllowance));
      const graphWidth = Math.max(1, maxX - minX);
      const graphHeight = Math.max(1, maxY - minY);
      const padX = dense ? 30 : compact ? 34 : 54;
      const padY = dense ? 28 : compact ? 28 : 48;
      const scale = Math.max(dense ? .24 : .42, Math.min(
        dense ? 1.08 : compact ? 1.22 : 1.34,
        (width - padX * 2) / graphWidth,
        (height - padY * 2) / graphHeight,
      ));
      const cx = (minX + maxX) / 2;
      const cy = (minY + maxY) / 2;
      svg.call(zoom.transform, d3.zoomIdentity.translate(width / 2 - scale * cx, height / 2 - scale * cy).scale(scale));
    }

    simulation.on("tick", renderTick);

    const drag = d3.drag<SVGGElement, SimNode>()
      .on("start", (event, item) => {
        if (!event.active) simulation.alpha(dense ? .16 : .22).alphaTarget(dense ? .055 : .09).restart();
        item.fx = item.x;
        item.fy = item.y;
      })
      .on("drag", (event, item) => {
        item.fx = event.x;
        item.fy = event.y;
      })
      .on("end", (event, item) => {
        if (!event.active) simulation.alphaTarget(0);
        item.fx = null;
        item.fy = null;
      });
    node.call(drag);

    // Small graphs receive a short organic settle. Dense graphs remain static until the
    // user drags a node, avoiding continuous CPU/SVG churn while preserving full physics.
    if (!dense) simulation.alpha(.07).restart();

    svg.on("dblclick.zoom", null);
    return () => {
      simulation.stop();
      svg.on(".zoom", null);
    };
  }, [nodes, edges, risks, insights, compact, expanded, resetToken, viewport, dense]);

  useEffect(() => {
    const svgElement = svgRef.current;
    if (!svgElement) return;
    const svg = d3.select(svgElement);
    const neighborIds = new Set<string>();
    if (selectedId) {
      neighborIds.add(selectedId);
      for (const edge of edges) {
        if (edge.source_id === selectedId) neighborIds.add(edge.target_id);
        if (edge.target_id === selectedId) neighborIds.add(edge.source_id);
      }
    }
    svg.selectAll<SVGGElement, SimNode>(".force-node")
      .classed("selected", (item) => item.id === selectedId)
      .style("opacity", (item) => !selectedId || neighborIds.has(item.id) ? 1 : dense ? .32 : .18);
    svg.selectAll<SVGElement, SimLink>(".force-link")
      .style("opacity", (item) => {
        if (!selectedId) return dense ? .16 : 1;
        const source = endpointId(item.source as string | number | SimNode);
        const target = endpointId(item.target as string | number | SimNode);
        return source === selectedId || target === selectedId ? 1 : dense ? .025 : .1;
      });

    if (dense) {
      const allNodes = svg.selectAll<SVGGElement, SimNode>(".force-node").data();
      const selectedNode = allNodes.find((item) => item.id === selectedId);
      const labelIds = new Set<string>();
      if (selectedId) {
        labelIds.add(selectedId);
        if (labelMode === "selection") for (const id of neighborIds) labelIds.add(id);
      }
      const occupied: Array<{ left: number; right: number; top: number; bottom: number }> = [];
      const nodeBoxes = allNodes.map((item) => {
        const radius = nodeRadius(item, undefined, undefined, true) + 7;
        return { id: item.id, left: (item.x ?? 0) - radius, right: (item.x ?? 0) + radius, top: (item.y ?? 0) - radius, bottom: (item.y ?? 0) + radius };
      });
      const overlaps = (a: { left: number; right: number; top: number; bottom: number }, b: { left: number; right: number; top: number; bottom: number }) => !(a.right < b.left || a.left > b.right || a.bottom < b.top || a.top > b.bottom);

      const visible = allNodes.filter((item) => labelIds.has(item.id));
      visible.sort((a, b) => a.id === selectedId ? -1 : b.id === selectedId ? 1 : a.id.localeCompare(b.id));
      const placement = new Map<string, { x: number; y: number; anchor: "start" | "middle" | "end" }>();
      for (const item of visible) {
        const radius = nodeRadius(item, undefined, undefined, true);
        const sx = selectedNode?.x ?? item.x ?? 0;
        const sy = selectedNode?.y ?? item.y ?? 0;
        const dx = (item.x ?? 0) - sx;
        const dy = (item.y ?? 0) - sy;
        const mag = Math.max(1, Math.hypot(dx, dy));
        const ux = dx / mag;
        const uy = dy / mag;
        const outward = item.id === selectedId ? { x: 0, y: 1 } : { x: ux, y: uy };
        const labelText = item.label.length > 30 ? `${item.label.slice(0, 29)}…` : item.label;
        const width = Math.min(190, Math.max(54, labelText.length * 6.1));
        const height = 15;
        const base = radius + 10;
        const candidates = [base, base + 12, base + 24, base + 38].flatMap((distance) => [0, 14, -14].map((side) => {
          const px = outward.x * distance + (-outward.y) * side;
          const py = outward.y * distance + outward.x * side;
          const anchor: "start" | "middle" | "end" = Math.abs(outward.x) < .32 ? "middle" : outward.x > 0 ? "start" : "end";
          return { x: px, y: py, anchor };
        }));
        let chosen = candidates[0];
        for (const candidate of candidates) {
          const gx = (item.x ?? 0) + candidate.x;
          const gy = (item.y ?? 0) + candidate.y;
          const left = candidate.anchor === "start" ? gx : candidate.anchor === "end" ? gx - width : gx - width / 2;
          const box = { left, right: left + width, top: gy - height / 2, bottom: gy + height / 2 };
          const hitsLabel = occupied.some((other) => overlaps(box, other));
          const hitsNode = nodeBoxes.some((other) => other.id !== item.id && overlaps(box, other));
          if (!hitsLabel && !hitsNode) { chosen = candidate; occupied.push(box); break; }
        }
        placement.set(item.id, chosen);
      }

      svg.selectAll<SVGTextElement, SimNode>(".dense-context-label")
        .style("opacity", (item) => labelIds.has(item.id) ? 1 : 0)
        .attr("x", (item) => placement.get(item.id)?.x ?? 0)
        .attr("y", (item) => placement.get(item.id)?.y ?? 0)
        .attr("text-anchor", (item) => placement.get(item.id)?.anchor ?? "middle");
    }
  }, [selectedId, edges, resetToken, dense, labelMode]);

  const classes = ["force-graph", compact ? "compact" : "", dense ? "dense" : "", expanded ? "expanded" : ""].filter(Boolean).join(" ");
  return <svg ref={svgRef} className={classes} aria-label="Interactive enterprise cryptographic dependency graph" />;
}
