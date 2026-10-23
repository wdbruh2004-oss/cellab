import os

import pytest

os.environ.setdefault("QT_API", "pyside6")

from cellab.model.cell_model import build_cell_model  # noqa: E402
from cellab.science.knowledge import KnowledgeBase  # noqa: E402
from cellab.science.profile import CellProfile  # noqa: E402


@pytest.fixture(scope="session")
def kb() -> KnowledgeBase:
    return KnowledgeBase.load()


@pytest.fixture(scope="session")
def profile() -> CellProfile:
    return CellProfile.load()


@pytest.fixture(scope="session")
def model(profile):
    return build_cell_model(profile)
