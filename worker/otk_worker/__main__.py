"""Entry point: `python -m otk_worker` serves JSON-RPC on stdin/stdout."""

from . import api
from .rpc import stdio_server


def main() -> None:
    server = stdio_server()
    api.register(server)
    server.serve_forever()


if __name__ == "__main__":
    main()
