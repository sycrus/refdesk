import pytest

from refdesk.api.app import app, get_service


@pytest.fixture(autouse=True)
def no_real_board_service(monkeypatch):
    """API tests never touch the real store (data/refdesk.sqlite) or load the real
    retriever. A test that needs the board service overrides this with its own.
    Startup auto-resume (issue #157) is off: a lifespan-running test would otherwise
    resume the real store's runs. Tests of the resume turn it back on explicitly."""

    monkeypatch.setenv("REFDESK_AUTO_RESUME", "0")

    def refuse():
        pytest.fail("this test reached the real board service; override get_service")

    app.dependency_overrides[get_service] = refuse
    yield
    app.dependency_overrides.clear()
