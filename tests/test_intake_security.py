from pathlib import Path

import pytest
from fastapi import HTTPException

from ecdat.api.routes.intake import _safe_member_path


def test_safe_archive_member_stays_under_intake_root(tmp_path: Path) -> None:
    target = _safe_member_path(tmp_path, "repository/src/app.py")
    assert target == (tmp_path / "repository/src/app.py").resolve()


@pytest.mark.parametrize("name", ["../secret", "../../etc/passwd", "/absolute/path", "repository/../../../escape"])
def test_unsafe_archive_members_are_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(HTTPException):
        _safe_member_path(tmp_path, name)
