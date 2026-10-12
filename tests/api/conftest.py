import pytest

from refdesk.api.app import app, get_service


@pytest.fixture(autouse=True)
def no_real_board_service():
    """API tests never touch the real store (data/refdesk.sqlite) or load the real
    retriever. A test that needs the board service overrides this with its own."""

    def refuse():
        pytest.fail("this test reached the real board service; override get_service")

    app.dependency_overrides[get_service] = refuse
    yield
    app.dependency_overrides.clear()
