"use client";

import * as d3 from "d3";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { GraphEdge, GraphInsight, GraphNode, RiskAssessment } from "@/lib/types";

type SimNode = GraphNode & d3.SimulationNodeDatum;
type SimLink = d3.SimulationLinkDatum<SimNode> & GraphEdge;

function nodeRadius(node: GraphNode, insight?: GraphInsight) {
  const base = node.node_type === "service" ? 12 : node.node_type === "data_class" ? 9 : 7;
  return base + Math.min(9, (insight?.centrality ?? 0) * 9);
}

function riskForNode(node: GraphNode, riskByAsset: Map<string, RiskAssessment>) {
  if (!node.id.startsWith("asset:")) return undefined;
  return riskByAsset.get(node.id.slice("asset:".length));
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
  resetToken = 0,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  risks: RiskAssessment[];
  insights: GraphInsight[];
  selectedId?: string | null;
  onSelect?: (node: GraphNode) => void;
  compact?: boolean;
  resetToken?: number;
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const onSelectRef = useRef(onSelect);
  const edgeDataRef = useRef<SimLink[]>([]);
  const [viewport, setViewport] = useState(() => ({ width: compact ? 760 : 1180, height: compact ? 405 : 700 }));

  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);

  useLayoutEffect(() => {
    const element = svgRef.current;
    if (!element) return;
    const update = () => {
      const rect = element.getBoundingClientRect();
      const width = Math.max(compact ? 520 : 720, Math.round(rect.width));
      const height = Math.max(compact ? 340 : 560, Math.round(rect.height));
      setViewport((current) => Math.abs(current.width - width) < 4 && Math.abs(current.height - height) < 4 ? current : { width, height });
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, [compact]);

  useEffect(() => {
    const svgElement = svgRef.current;
    if (!svgElement || nodes.length === 0) return;

    const { width, height } = viewport;
    const suffix = `${compact ? "c" : "f"}-${resetToken}`;
    const svg = d3.select(svgElement);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const defs = svg.append("defs");
    const glow = defs.append("filter").attr("id", `node-glow-${suffix}`).attr("x", "-80%").attr("y", "-80%").attr("width", "260%").attr("height", "260%");
    glow.append("feGaussianBlur").attr("stdDeviation", compact ? 2.2 : 3.5).attr("result", "blur");
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
      .attr("fill", "rgba(255,104,58,.48)");

    const root = svg.append("g").attr("class", "force-root");
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.35, 3.6])
      .on("zoom", (event) => root.attr("transform", event.transform));
    svg.call(zoom);
    svg.call(zoom.transform, d3.zoomIdentity);

    const riskByAsset = new Map(risks.map((risk) => [risk.asset_id, risk]));
    const insightByNode = new Map(insights.map((insight) => [insight.node_id, insight]));
    const simNodes: SimNode[] = nodes.map((node, index) => ({ ...node, ...seededPosition(node.id, index, nodes.length, width, height) }));
    const nodeIds = new Set(nodes.map((node) => node.id));
    const simLinks: SimLink[] = edges
      .filter((edge) => nodeIds.has(edge.source_id) && nodeIds.has(edge.target_id))
      .map((edge) => ({ ...edge, source: edge.source_id, target: edge.target_id }));
    edgeDataRef.current = simLinks;

    const link = root.append("g").attr("class", "force-links")
      .selectAll<SVGPathElement, SimLink>("path")
      .data(simLinks)
      .join("path")
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
        return `force-node type-${item.node_type}${risk ? ` risk-${risk.priority}` : ""}${blocker}`;
      })
      .style("cursor", onSelectRef.current ? "pointer" : "grab")
      .on("click", (event, item) => {
        event.stopPropagation();
        onSelectRef.current?.(nodes.find((candidate) => candidate.id === item.id) ?? item);
      });

    node.filter((item) => insightByNode.get(item.id)?.migration_blocker === true)
      .append("circle")
      .attr("class", "blocker-ring")
      .attr("r", (item) => nodeRadius(item, insightByNode.get(item.id)) + 10);

    node.filter((item) => Boolean(riskForNode(item, riskByAsset)))
      .append("circle")
      .attr("class", (item) => {
        const risk = riskForNode(item, riskByAsset);
        return `node-risk-ring priority-${risk?.priority ?? "unknown"}`;
      })
      .attr("r", (item) => nodeRadius(item, insightByNode.get(item.id)) + 4.5);

    node.append("circle")
      .attr("class", "node-disc")
      .attr("r", (item) => nodeRadius(item, insightByNode.get(item.id)))
      .attr("filter", `url(#node-glow-${suffix})`);

    node.append("circle")
      .attr("class", "node-core")
      .attr("r", (item) => Math.max(2.8, nodeRadius(item, insightByNode.get(item.id)) * .28));

    if (!compact) {
      node.append("text")
        .attr("class", "force-label")
        .attr("text-anchor", "middle")
        .attr("dy", (item) => nodeRadius(item, insightByNode.get(item.id)) + 15)
        .text((item) => item.label.length > 24 ? `${item.label.slice(0, 23)}…` : item.label);
      node.append("text")
        .attr("class", "force-type")
        .attr("text-anchor", "middle")
        .attr("dy", (item) => nodeRadius(item, insightByNode.get(item.id)) + 29)
        .text((item) => item.node_type.replaceAll("_", " "));
    }

    const simulation = d3.forceSimulation<SimNode>(simNodes)
      .alpha(0.92)
      .alphaDecay(0.035)
      .force("link", d3.forceLink<SimNode, SimLink>(simLinks).id((item) => item.id).distance((item) => {
        if (item.edge_type === "uses") return compact ? 66 : 118;
        if (item.edge_type === "protects") return compact ? 76 : 138;
        return compact ? 92 : 162;
      }).strength(compact ? .5 : .43))
      .force("charge", d3.forceManyBody().strength(compact ? -300 : -760))
      .force("collision", d3.forceCollide<SimNode>().radius((item) => nodeRadius(item, insightByNode.get(item.id)) + (compact ? 14 : 32)))
      .force("x", d3.forceX(width / 2).strength(compact ? .035 : .026))
      .force("y", d3.forceY(height / 2).strength(compact ? .04 : .028))
      .force("center", d3.forceCenter(width / 2, height / 2));

    const drag = d3.drag<SVGGElement, SimNode>()
      .on("start", (event, item) => {
        if (!event.active) simulation.alphaTarget(.22).restart();
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

    const renderTick = () => {
      link.attr("d", (item) => {
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
      node.attr("transform", (item) => `translate(${item.x ?? 0},${item.y ?? 0})`);
    };

    // Settle deterministically before the first paint, then fit the actual graph bounds
    // to the rendered viewport. This keeps dense enterprise graphs from occupying only
    // the upper portion of an otherwise available canvas while preserving zoom/drag.
    simulation.stop();
    simulation.tick(compact ? 90 : 130);
    renderTick();

    if (simNodes.length > 1) {
      const labelAllowance = compact ? 8 : 34;
      const minX = Math.min(...simNodes.map((item) => (item.x ?? width / 2) - nodeRadius(item, insightByNode.get(item.id)) - 12));
      const maxX = Math.max(...simNodes.map((item) => (item.x ?? width / 2) + nodeRadius(item, insightByNode.get(item.id)) + 12));
      const minY = Math.min(...simNodes.map((item) => (item.y ?? height / 2) - nodeRadius(item, insightByNode.get(item.id)) - 12));
      const maxY = Math.max(...simNodes.map((item) => (item.y ?? height / 2) + nodeRadius(item, insightByNode.get(item.id)) + labelAllowance));
      const graphWidth = Math.max(1, maxX - minX);
      const graphHeight = Math.max(1, maxY - minY);
      const padX = compact ? 34 : 54;
      const padY = compact ? 28 : 48;
      const scale = Math.max(.42, Math.min(
        compact ? 1.22 : 1.34,
        (width - padX * 2) / graphWidth,
        (height - padY * 2) / graphHeight,
      ));
      const cx = (minX + maxX) / 2;
      const cy = (minY + maxY) / 2;
      const transform = d3.zoomIdentity
        .translate(width / 2 - scale * cx, height / 2 - scale * cy)
        .scale(scale);
      svg.call(zoom.transform, transform);
    }

    simulation.on("tick", renderTick).alpha(compact ? .08 : .1).restart();

    svg.on("dblclick.zoom", null);
    return () => {
      simulation.stop();
      svg.on(".zoom", null);
    };
  }, [nodes, edges, risks, insights, compact, resetToken, viewport]);

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
      .style("opacity", (item) => !selectedId || neighborIds.has(item.id) ? 1 : .18);
    svg.selectAll<SVGPathElement, SimLink>(".force-link")
      .style("opacity", (item) => {
        if (!selectedId) return 1;
        const source = endpointId(item.source as string | number | SimNode);
        const target = endpointId(item.target as string | number | SimNode);
        return source === selectedId || target === selectedId ? 1 : .1;
      });
  }, [selectedId, edges, resetToken]);

  return <svg ref={svgRef} className={compact ? "force-graph compact" : "force-graph"} aria-label="Interactive enterprise cryptographic dependency graph" />;
}
