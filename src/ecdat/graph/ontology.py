from uuid import UUID

from ecdat.domain.enums import GraphEdgeType, GraphNodeType
from ecdat.domain.models import CryptoAsset, GraphEdge, GraphNode, ScanTarget


def target_node(target: ScanTarget) -> GraphNode:
    # A combined assessment is a scope/container, not itself a repository. Keeping
    # that distinction prevents the assessment root from being mistaken for an
    # owned engineering system in graph/readiness analysis.
    if isinstance(target.metadata.get("sources"), list):
        node_type = GraphNodeType.INFRASTRUCTURE
    else:
        node_type = GraphNodeType.REPOSITORY if target.kind.value in {"repository", "directory"} else GraphNodeType.INFRASTRUCTURE
    return GraphNode(
        id=f"target:{target.kind}:{target.locator}",
        node_type=node_type,
        label=target.display_name or target.locator,
        properties={"target_kind": target.kind.value},
    )


def asset_node(asset: CryptoAsset) -> GraphNode:
    type_map = {
        "algorithm": GraphNodeType.ALGORITHM,
        "library": GraphNodeType.LIBRARY,
        "certificate": GraphNodeType.CERTIFICATE,
        "key": GraphNodeType.KEY,
        "protocol": GraphNodeType.PROTOCOL,
    }
    return GraphNode(
        id=f"asset:{asset.id}",
        node_type=type_map.get(asset.asset_type.value, GraphNodeType.CRYPTO_ASSET),
        label=asset.canonical_name,
        properties={
            "asset_type": asset.asset_type.value,
            "version": asset.version,
            "algorithm_family": asset.algorithm_family,
            "key_size_bits": asset.key_size_bits,
        },
    )


def target_uses_asset_edge(target_id: str, asset_id: UUID) -> GraphEdge:
    return GraphEdge(
        id=f"uses:{target_id}:asset:{asset_id}",
        source_id=target_id,
        target_id=f"asset:{asset_id}",
        edge_type=GraphEdgeType.USES,
    )
