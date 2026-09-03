from fastapi.testclient import TestClient

from ecdat.api.app import create_app


def test_health_contract_has_product_version() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ecdat-api", "version": "1.0.0"}


def test_scanner_catalog_exposes_real_discovery_adapters() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/v1/scanners")
    assert response.status_code == 200
    ids = {item["scanner_id"] for item in response.json()}
    assert {"source.static", "dependencies.manifest", "protocols.config", "certificates.x509", "binaries.heuristic", "containers.dockerfile"}.issubset(ids)
