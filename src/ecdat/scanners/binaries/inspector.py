from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from typing import Iterable

_PRINTABLE = re.compile(rb"[ -~]{5,}")


@dataclass(frozen=True, slots=True)
class BinaryProfile:
    format: str
    bits: int | None = None
    architecture: str | None = None
    likely_stripped: bool = False
    opaque_or_packed_signal: bool = False

    def as_attributes(self) -> dict[str, object]:
        return {
            "binary_format": self.format,
            "binary_bits": self.bits,
            "binary_architecture": self.architecture,
            "likely_stripped": self.likely_stripped,
            "opaque_or_packed_signal": self.opaque_or_packed_signal,
        }


def looks_binary(prefix: bytes, *, filename: str = "") -> bool:
    lower = filename.lower()
    return (
        prefix.startswith(b"\x7fELF")
        or prefix.startswith(b"MZ")
        or prefix.startswith(b"!<arch>\n")
        or prefix[:4] in {b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"}
        or b"\x00" in prefix[:1024]
        or lower.endswith((".so", ".dll", ".dylib", ".exe", ".bin", ".elf", ".a"))
    )


def profile_binary(raw: bytes) -> BinaryProfile:
    fmt = "unknown"
    bits: int | None = None
    architecture: str | None = None
    if raw.startswith(b"\x7fELF") and len(raw) >= 20:
        fmt = "ELF"
        bits = {1: 32, 2: 64}.get(raw[4])
        endian = "<" if raw[5] == 1 else ">"
        try:
            machine = struct.unpack_from(f"{endian}H", raw, 18)[0]
            architecture = {
                3: "x86", 40: "ARM", 62: "x86_64", 183: "AArch64", 243: "RISC-V",
            }.get(machine, f"ELF-machine-{machine}")
        except struct.error:
            pass
    elif raw.startswith(b"MZ"):
        fmt = "PE"
        try:
            pe_offset = struct.unpack_from("<I", raw, 0x3C)[0]
            if raw[pe_offset:pe_offset + 4] == b"PE\x00\x00":
                machine = struct.unpack_from("<H", raw, pe_offset + 4)[0]
                architecture = {0x14C: "x86", 0x8664: "x86_64", 0x1C0: "ARM", 0xAA64: "AArch64"}.get(machine, f"PE-machine-{machine:#x}")
                optional_magic = struct.unpack_from("<H", raw, pe_offset + 24)[0]
                bits = 64 if optional_magic == 0x20B else 32 if optional_magic == 0x10B else None
        except (struct.error, IndexError):
            pass
    elif raw[:4] in {b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe"}:
        fmt, bits = "Mach-O", 32
    elif raw[:4] in {b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe"}:
        fmt, bits = "Mach-O", 64
    elif raw.startswith(b"!<arch>\n"):
        fmt = "static-archive"

    strings = _PRINTABLE.findall(raw[:250_000])
    nul_ratio = raw[:64_000].count(b"\x00") / max(1, len(raw[:64_000]))
    likely_stripped = fmt in {"ELF", "PE", "Mach-O"} and len(strings) < 8
    opaque = nul_ratio > 0.35 and len(strings) < 5
    return BinaryProfile(fmt, bits, architecture, likely_stripped, opaque)


def printable_blob(raw: bytes) -> bytes:
    return b"\n".join(_PRINTABLE.findall(raw))


def iter_ar_members(raw: bytes) -> Iterable[tuple[str, bytes]]:
    """Yield basic UNIX ar members without executing external tooling.

    GNU/BSD long-name tables are tolerated as metadata members; unresolved long names
    remain synthetic labels rather than causing the whole archive to be skipped.
    """
    if not raw.startswith(b"!<arch>\n"):
        return
    offset = 8
    index = 0
    while offset + 60 <= len(raw):
        header = raw[offset:offset + 60]
        if header[58:60] != b"`\n":
            break
        name = header[:16].decode("ascii", errors="replace").strip().rstrip("/")
        try:
            size = int(header[48:58].decode("ascii", errors="ignore").strip() or "0")
        except ValueError:
            break
        start = offset + 60
        end = min(len(raw), start + size)
        payload = raw[start:end]
        if name not in {"", "/", "//", "__.SYMDEF", "__.SYMDEF SORTED"}:
            yield name or f"member-{index}", payload
        index += 1
        offset = end + (size % 2)
