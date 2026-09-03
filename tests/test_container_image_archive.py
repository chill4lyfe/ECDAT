import io
import json
import tarfile
from pathlib import Path

from ecdat.domain.enums import TargetKind
from ecdat.domain.models import ScanRequest, ScanTarget
from ecdat.scanners.containers.image_archive import ContainerImageArchiveScanner


def _build_image_archive(path: Path) -> None:
    layer_buffer = io.BytesIO()
    with tarfile.open(fileobj=layer_buffer, mode="w") as layer:
        package_payload = b"Package: openssl\nVersion: 3.0.13-r0\n\n"
        package_info = tarfile.TarInfo("lib/apk/db/installed")
        package_info.size = len(package_payload)
        layer.addfile(package_info, io.BytesIO(package_payload))

        library_payload = b"\x7fELF\x00OpenSSL"
        library_info = tarfile.TarInfo("usr/lib/libcrypto.so.3")
        library_info.size = len(library_payload)
        layer.addfile(library_info, io.BytesIO(library_payload))
    layer_bytes = layer_buffer.getvalue()

    with tarfile.open(path, mode="w") as outer:
        manifest = json.dumps([{"Config": "config.json", "RepoTags": ["test:latest"], "Layers": ["layer.tar"]}]).encode()
        manifest_info = tarfile.TarInfo("manifest.json")
        manifest_info.size = len(manifest)
        outer.addfile(manifest_info, io.BytesIO(manifest))

        layer_info = tarfile.TarInfo("layer.tar")
        layer_info.size = len(layer_bytes)
        outer.addfile(layer_info, io.BytesIO(layer_bytes))


async def test_container_image_archive_scanner_inspects_layers_without_execution(tmp_path: Path) -> None:
    archive = tmp_path / "image.tar"
    _build_image_archive(archive)
    request = ScanRequest(target=ScanTarget(kind=TargetKind.CONTAINER_IMAGE, locator=str(archive), display_name="offline image"))
    findings = await ContainerImageArchiveScanner().scan(request)
    assert findings
    assert any(item.asset.canonical_name in {"OpenSSL", "OpenSSL/libcrypto"} for item in findings)
    assert all(item.evidence[0].attributes["offline_inspection"] is True for item in findings)
