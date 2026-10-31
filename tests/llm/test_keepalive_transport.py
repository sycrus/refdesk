"""KeepAliveTransport reuses one connection per host (issue #161: thousands of fresh
connections exhausted Windows' ephemeral ports, WinError 10048)."""

import json

import pytest

from refdesk.llm import client as llm


class FakeResponse:
    def __init__(self, status, body):
        self.status, self._body = status, body

    def read(self):
        return self._body


class FakeConn:
    def __init__(self, fail_first=0):
        self.requests, self.fail_first, self.closed = 0, fail_first, False

    def request(self, method, path, body, headers):
        self.requests += 1
        if self.fail_first:
            self.fail_first -= 1
            raise ConnectionResetError("dropped")
        self.path = path

    def getresponse(self):
        return FakeResponse(200, json.dumps({"ok": True}).encode())

    def close(self):
        self.closed = True


def test_one_connection_is_reused_for_many_requests():
    opened = []

    def connect(scheme, host, timeout):
        opened.append(FakeConn())
        return opened[-1]

    t = llm.KeepAliveTransport(connect=connect)
    for _ in range(50):
        assert t.post_json("http://127.0.0.1:8100/v1/chat/completions", {}, {}) == (
            200, {"ok": True},
        )  # fmt: skip
    assert len(opened) == 1
    assert opened[0].requests == 50
    assert opened[0].path == "/v1/chat/completions"


def test_a_dropped_connection_is_reopened_once_then_an_error():
    opened = []

    def connect(scheme, host, timeout):
        opened.append(FakeConn(fail_first=1))
        return opened[-1]

    t = llm.KeepAliveTransport(connect=connect)
    with pytest.raises(llm.ProviderError):
        t.post_json("http://h/v1/x", {}, {})  # both attempts drop
    assert len(opened) == 2 and all(c.closed for c in opened)


def test_a_timeout_is_a_provider_timeout():
    class Slow(FakeConn):
        def getresponse(self):
            raise TimeoutError

    t = llm.KeepAliveTransport(connect=lambda *a: Slow())
    with pytest.raises(llm.ProviderTimeout):
        t.post_json("http://h/v1/x", {}, {})
