"""Resolve forwarded addresses once while the original transport peer is intact."""

from functools import lru_cache
from ipaddress import ip_address, ip_network


def address(value):
    if "%" in value:
        raise ValueError("Scoped addresses are not accepted")
    parsed = ip_address(value.strip())
    return getattr(parsed, "ipv4_mapped", None) or parsed


@lru_cache(maxsize=64)
def networks(config):
    return tuple(
        ip_network(value.strip(), strict=False)
        for value in config.split(",")
        if value.strip() and value.strip() != "*"
    )


def client_ip(scope, trusted_proxies=""):
    peer = (scope.get("client") or ("unknown", 0))[0]
    try:
        direct = address(peer)
        trusted = networks(trusted_proxies)
    except ValueError:
        return peer
    wildcard = trusted_proxies.strip() == "*"
    if not wildcard and not any(direct in network for network in trusted):
        return str(direct)
    headers = [
        value for key, value in scope.get("headers", []) if key.lower() == b"x-forwarded-for"
    ]
    if len(headers) != 1 or len(headers[0]) > 4096:
        return str(direct)
    try:
        chain = [address(value) for value in headers[0].decode("ascii").split(",")]
        if not chain or len(chain) > 32:
            return str(direct)
    except (ValueError, UnicodeError):
        return str(direct)
    # '*' trusts the controlled direct ingress only, not arbitrary addresses
    # supplied earlier in the chain. Multi-hop trust requires explicit CIDRs.
    for candidate in reversed(chain):
        if not any(candidate in network for network in trusted):
            return str(candidate)
    return str(direct)
