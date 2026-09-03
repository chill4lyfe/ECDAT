from typing import Protocol

from ecdat.domain.models import ScanSummary


class ReportRenderer(Protocol):
    media_type: str

    def render(self, summary: ScanSummary) -> bytes: ...
