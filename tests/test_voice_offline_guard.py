"""Exercise real socket audit events with no external packet or provider I/O."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


GUARD = Path(__file__).resolve().parent / "voice_lab" / "offline_guard"


class OfflineGuardTests(unittest.TestCase):
    def child(self, code):
        # Do not pass credentials or live-enabling flags into child processes.
        return subprocess.run(
            [sys.executable, "-c", code], text=True, capture_output=True,
            timeout=10,
            env={"PATH": os.environ.get("PATH", ""),
                 "PYTHONPATH": str(GUARD), "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def test_external_tcp_is_refused_before_connecting(self):
        result = self.child("import socket; socket.socket().connect(('203.0.113.1', 443))")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Outbound network disabled", result.stderr)

    def test_external_dns_is_refused(self):
        for call in ("socket.getaddrinfo('offline-validation.invalid', 443)",
                     "socket.gethostbyname('offline-validation.invalid')",
                     "socket.gethostbyaddr('203.0.113.1')",
                     "socket.getnameinfo(('203.0.113.1',443),0)"):
            with self.subTest(call=call):
                result = self.child("import socket; " + call)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("External DNS disabled", result.stderr)

    def test_external_udp_is_refused_before_sending(self):
        for send in ("s.sendto(b'test',('203.0.113.1',53))",
                     "s.sendmsg([b'test'],[],0,('203.0.113.1',53))"):
            with self.subTest(send=send):
                result = self.child("import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); " + send)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Outbound network disabled", result.stderr)

    def test_loopback_and_unix_sockets_remain_usable(self):
        result = self.child(
            "import socket; a,b=socket.socketpair(); a.close(); b.close(); "
            "server=socket.socket(); server.bind(('127.0.0.1',0)); server.listen(); "
            "client=socket.socket(); client.connect(server.getsockname()); "
            "client.close(); server.close()"
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
