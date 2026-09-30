"""Bring up the loopback interface inside a fresh network namespace (Linux).

Used by scripts/test-offline.sh: Playwright drives Electron over a debugging
connection on 127.0.0.1, so the harness needs loopback. No other interface
exists, so nothing can leave the machine.
"""
import fcntl
import socket
import struct

SIOCGIFFLAGS, SIOCSIFFLAGS, IFF_UP = 0x8913, 0x8914, 0x1
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
ifreq = fcntl.ioctl(s, SIOCGIFFLAGS, struct.pack("16sH14x", b"lo", 0))
flags = struct.unpack("16sH14x", ifreq)[1]
fcntl.ioctl(s, SIOCSIFFLAGS, struct.pack("16sH14x", b"lo", flags | IFF_UP))
print("loopback up")
