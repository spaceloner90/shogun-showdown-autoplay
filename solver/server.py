"""The solver server: keeps worker processes warm so the deeper searches can split across cores on every key press.

The mod starts solver/analyze.py for each request, and that asks this server over a local socket (`ask`). If no
server answers, analyze.py starts one in the background and answers that request itself, single-core. The server
compares the solver's source files with the ones it started from on every request, and when they differ it quits
instead of answering, so the next press starts a fresh one: code changes still apply on the next key press. It also
quits after IDLE_SECONDS without a request.

    python solver/server.py      # run it in the foreground, to watch it
"""
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = 47621
IDLE_SECONDS = 3 * 3600
WORKERS = max(1, (os.cpu_count() or 2) - 2)
LOG = Path(tempfile.gettempdir()) / "shogun_solver_server.log"


def code_stamp():
    """The solver's source files, by modification time: the server only answers requests from the same code."""
    return ";".join(f"{p.name}:{p.stat().st_mtime_ns}" for p in sorted(HERE.glob("*.py")))


def _send(sock, data):
    sock.sendall(struct.pack(">I", len(data)) + data)


def _receive(sock):
    header = b""
    while len(header) < 4:
        chunk = sock.recv(4 - len(header))
        if not chunk:
            return None
        header += chunk
    size = struct.unpack(">I", header)[0]
    data = b""
    while len(data) < size:
        chunk = sock.recv(min(1 << 16, size - len(data)))
        if not chunk:
            return None
        data += chunk
    return data


def start_in_background():
    # A hidden console rather than none: a process with no console gives each worker it starts a console window of
    # its own, which popped up on the player's screen.
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    with open(LOG, "ab") as log:
        subprocess.Popen([sys.executable, str(HERE / "server.py")], cwd=str(HERE), stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, creationflags=flags, close_fds=True)


def ask(row_text, timeout=60.0):
    """The server's answer to a request, or None if no server running this code could answer; then one is started."""
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.2) as sock:
            sock.settimeout(timeout)
            _send(sock, json.dumps({"stamp": code_stamp(), "row": row_text}).encode("utf-8"))
            reply = _receive(sock)
    except OSError:
        start_in_background()
        return None
    if reply is None or reply == b"RESTART":
        start_in_background()
        return None
    return reply.decode("utf-8")


def _warm():
    sys.path.insert(0, str(HERE))
    import search  # noqa: F401 - imported once per worker, not per task


def serve():
    import analyze
    stamp = code_stamp()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", PORT))
    except OSError:
        print("another server already has the port", flush=True)
        return
    listener.listen(4)
    listener.settimeout(60)
    pool = ProcessPoolExecutor(max_workers=WORKERS, initializer=_warm)
    list(pool.map(abs, range(WORKERS * 2)))  # start every worker now, not on the first request
    print(f"{time.ctime()}: serving on {PORT} with {WORKERS} workers", flush=True)
    last = time.time()
    try:
        while time.time() - last < IDLE_SECONDS:
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            last = time.time()
            with connection:
                connection.settimeout(60)
                request = _receive(connection)
                if request is None:
                    continue
                request = json.loads(request.decode("utf-8"))
                if request["stamp"] != stamp or code_stamp() != stamp:
                    _send(connection, b"RESTART")
                    print(f"{time.ctime()}: solver code changed, quitting", flush=True)
                    return
                try:
                    text = analyze.answer(json.loads(request["row"]), pool)
                except Exception as error:  # noqa: BLE001 - report it, keep serving
                    print(f"{time.ctime()}: {error!r}", flush=True)
                    _send(connection, b"RESTART")
                    return
                _send(connection, text.encode("utf-8"))
    finally:
        pool.shutdown(cancel_futures=True)
        listener.close()


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    serve()
