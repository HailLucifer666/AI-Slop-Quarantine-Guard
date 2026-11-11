"""Rate limiting must count the end client, not the proxy in front of it."""

from starlette.requests import Request

from app.api_security import _client_ip


def _request(headers: dict, peer: str = "10.0.0.1") -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 1234)})


def test_forwarded_client_ip_is_preferred_over_the_proxy_peer():
    # Behind fly.io every caller's peer address is the proxy, so keying on it collapsed
    # the per-IP window into one global bucket shared by every user.
    a = _client_ip(_request({"Fly-Client-IP": "203.0.113.7"}))
    b = _client_ip(_request({"Fly-Client-IP": "198.51.100.9"}))
    assert (a, b) == ("203.0.113.7", "198.51.100.9")
    assert a != b, "two different clients must land in different rate-limit buckets"


def test_falls_back_to_the_peer_when_not_behind_a_proxy():
    assert _client_ip(_request({}, peer="127.0.0.1")) == "127.0.0.1"


def test_tolerates_a_comma_separated_forwarded_list():
    assert _client_ip(_request({"X-Real-IP": "203.0.113.7, 70.41.3.18"})) == "203.0.113.7"


def test_unknown_when_there_is_no_client_at_all():
    req = Request({"type": "http", "headers": [], "client": None})
    assert _client_ip(req) == "unknown"
