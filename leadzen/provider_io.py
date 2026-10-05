"""Bound provider response bodies by both bytes and a wall-clock deadline."""
import socket
import threading
import time


class ProviderResponseError(ValueError):
    pass


def read_response(connection, response, *, limit, deadline, description="Provider"):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProviderResponseError(f"{description} response deadline exceeded")
    # HTTP/1.0 and Connection: close detach the connection socket into the
    # response reader. Cover that socket too; closing only the connection would
    # leave a blocked worker thread reading a trickling response indefinitely.
    reader = getattr(getattr(response, "fp", None), "raw", None)
    sockets = [getattr(connection, "sock", None), getattr(reader, "_sock", None)]

    def abort():
        for sock in sockets:
            if sock is not None:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except (OSError, AttributeError):
                    pass

    timer = threading.Timer(remaining, abort)
    timer.daemon = True
    timer.start()
    data = bytearray()
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProviderResponseError(f"{description} response deadline exceeded")
            for sock in sockets:
                if sock is not None and hasattr(sock, "settimeout"):
                    sock.settimeout(remaining)
            chunk = response.read1(min(65536, limit + 1 - len(data)))
            if time.monotonic() >= deadline:
                raise ProviderResponseError(f"{description} response deadline exceeded")
            if not chunk:
                return bytes(data)
            data.extend(chunk)
            if len(data) > limit:
                raise ProviderResponseError(f"{description} response exceeded the limit")
    finally:
        timer.cancel()
