import pytest
from fastapi.testclient import TestClient

from app.client_ip import client_ip
from app.config import Settings
from app.main import create_app
from tests.fakes import FakeEmbedder, FakeLLM


def scope(peer, forwarded):
    return {"client": (peer, 123), "headers": [(b"x-forwarded-for", forwarded.encode())]}


@pytest.mark.parametrize(
    ("peer", "header", "trust", "expected"),
    [
        ("192.0.2.5", "198.51.100.1", "", "192.0.2.5"),
        ("192.0.2.5", "198.51.100.1", "10.0.0.0/8", "192.0.2.5"),
        ("10.0.0.1", "203.0.113.9, 198.51.100.1, 10.0.0.2", "10.0.0.0/8", "198.51.100.1"),
        ("10.0.0.1", "spoofed, 198.51.100.1", "*", "10.0.0.1"),
        ("10.0.0.1", "203.0.113.9, 198.51.100.1", "*", "198.51.100.1"),
        ("::1", "2001:db8::123, fd00::2", "::1/128,fd00::/8", "2001:db8::123"),
        ("::ffff:10.0.0.1", "198.51.100.1", "10.0.0.0/8", "198.51.100.1"),
        ("10.0.0.1", "198.51.100.1:80", "*", "10.0.0.1"),
        ("10.0.0.1", "198.51.100.1,", "*", "10.0.0.1"),
        ("10.0.0.1", "fe80::1%zone", "*", "10.0.0.1"),
    ],
)
def test_resolver(peer, header, trust, expected):
    assert client_ip(scope(peer, header), trust) == expected


def test_duplicate_headers_and_invalid_configuration_are_rejected():
    value = scope("10.0.0.1", "198.51.100.1")
    value["headers"] *= 2
    assert client_ip(value, "*") == "10.0.0.1"
    with pytest.raises(ValueError):
        Settings(_env_file=None, trusted_proxies="not-a-cidr")


def test_uvicorn_empty_trust_keeps_transport_peer_for_application():
    import asyncio

    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    captured = []

    async def receiver(value, receive, send):
        captured.append(value["client"][0])
        captured.append(client_ip(value, "10.0.0.0/8"))

    value = dict(scope("10.0.0.1", "198.51.100.1"), type="http", scheme="http")
    asyncio.run(ProxyHeadersMiddleware(receiver, trusted_hosts="")(value, None, None))
    assert captured == ["10.0.0.1", "198.51.100.1"]


def test_proxy_clients_get_separate_request_buckets(tmp_path):
    settings = Settings(
        _env_file=None, data_dir=tmp_path, trusted_proxies="*", ask_rate_per_minute=1
    )
    # The direct transport peer is preserved because Uvicorn performs no rewrite.
    with TestClient(
        create_app(settings, embedder=FakeEmbedder(), llm=FakeLLM()), client=("10.0.0.1", 1)
    ) as client:
        body = {"repoId": "missing", "question": "where?"}
        assert (
            client.post("/ask", json=body, headers={"X-Forwarded-For": "198.51.100.1"}).status_code
            == 404
        )
        assert (
            client.post("/ask", json=body, headers={"X-Forwarded-For": "198.51.100.2"}).status_code
            == 404
        )
        assert (
            client.post(
                "/ask", json=body, headers={"X-Forwarded-For": "spoofed,198.51.100.1"}
            ).status_code
            == 404
        )
        assert (
            client.post("/ask", json=body, headers={"X-Forwarded-For": "198.51.100.1"}).status_code
            == 429
        )
