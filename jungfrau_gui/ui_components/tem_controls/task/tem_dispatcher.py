import queue
import threading
import time
import logging

class TEMDispatcher:
    """
    Single-threaded command lane for TEM calls.
    - post(fn, ...): fire-and-forget
    - call(fn, ...): wait for result
    - post_sequence([...]): run multiple commands atomically (no interleave)
    - post_latest(key, fn, ...): keep only the newest request for a key (ideal for polling)
    """
    def __init__(self, client):
        self.client = client
        self._q = queue.Queue()
        self._stop = threading.Event()
        self._latest_token = {}  # key -> token
        self._thread = threading.Thread(target=self._loop, name="TEM-IO", daemon=True)
        self._thread.start()

    def shutdown(self):
        self._stop.set()
        self._q.put(None)

    def _loop(self):
        while not self._stop.is_set():
            item = self._q.get()
            if item is None:
                break

            kind = item[0]
            try:
                if kind == "call":
                    _, fn, args, kwargs, done, out = item
                    out["result"] = fn(*args, **kwargs)
                    done.set()

                elif kind == "post":
                    _, fn, args, kwargs = item
                    fn(*args, **kwargs)

                elif kind == "sequence":
                    _, fns = item
                    for fn, args, kwargs in fns:
                        fn(*args, **kwargs)

                elif kind == "latest":
                    _, key, token, fn, args, kwargs = item
                    # skip stale polls
                    if self._latest_token.get(key) == token:
                        fn(*args, **kwargs)

            except Exception as e:
                logging.warning(f"TEMDispatcher error in {kind}: {type(e).__name__}: {e}")

    def post(self, fn, *args, **kwargs):
        self._q.put(("post", fn, args, kwargs))

    def call(self, fn, *args, timeout=None, **kwargs):
        done = threading.Event()
        out = {}
        self._q.put(("call", fn, args, kwargs, done, out))
        ok = done.wait(timeout)
        return out.get("result") if ok else None

    def post_sequence(self, fns):
        """
        fns = [(fn, args_tuple, kwargs_dict), ...]
        executed back-to-back in the TEM thread.
        """
        self._q.put(("sequence", fns))

    def post_latest(self, key, fn, *args, **kwargs):
        token = object()
        self._latest_token[key] = token
        self._q.put(("latest", key, token, fn, args, kwargs))
