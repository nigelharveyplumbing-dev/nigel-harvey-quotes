"""Opt-in offline test process guard; never imported by production code.

Put this directory first on PYTHONPATH for test/preflight commands only.
Dependency installation is a separate step. Audit hooks survive mocked socket
methods used by protocol tests; only loopback and local Unix sockets are allowed.
"""
import ipaddress
import socket
import sys


def _local_host(host):
    if isinstance(host, bytes):
        host = host.decode("ascii", errors="replace")
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        return False


def _guard(event, args):
    if event in ("socket.connect", "socket.sendto", "socket.sendmsg"):
        sock, address = args[0], args[-1]
        if sock.family == socket.AF_UNIX:
            return
        if address is None:
            address = sock.getpeername()
        if not isinstance(address, tuple) or not _local_host(address[0]):
            raise RuntimeError("Outbound network disabled during offline voice validation")
    elif event in ("socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr"):
        if not _local_host(args[0]):
            raise RuntimeError("External DNS disabled during offline voice validation")
    elif event == "socket.getnameinfo":
        address = args[0]
        if not isinstance(address, tuple) or not _local_host(address[0]):
            raise RuntimeError("External DNS disabled during offline voice validation")


sys.addaudithook(_guard)
