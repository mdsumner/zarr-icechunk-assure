"""Deploy-axis test: the same built repo bytes, served over HTTP.

Proves the README Contract's second binding type executable: store host is
deploy-time and reversible -- nothing is rebuilt, nothing is renamed, only
the Repository.open line changes. This is the source.coop access pattern
(v2 fixed-key reads, GET-only, no LIST) reproduced against localhost.
"""
import http.server
import json
import pathlib
import socket
import threading

import pytest
import zarr
import icechunk as ic

import os

class RangeHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler + single-range GET (RFC 7233, bytes=)
    -- the minimum a store host needs for icechunk http storage."""

    def send_head(self):
        self._range = None
        spec = self.headers.get("Range", "")
        if spec.startswith("bytes=") and "," not in spec:
            lo, _, hi = spec[6:].partition("-")
            try:
                self._range = (int(lo) if lo else None, int(hi) if hi else None)
            except ValueError:
                self._range = None
        if self._range is None:
            return super().send_head()
        path = self.translate_path(self.path)
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404)
            return None
        size = os.fstat(f.fileno()).st_size
        lo, hi = self._range
        if lo is None:                       # suffix form: bytes=-N
            lo, hi = max(0, size - hi), size - 1
        else:
            hi = size - 1 if hi is None else min(hi, size - 1)
        if lo > hi or lo >= size:
            self.send_error(416)
            f.close()
            return None
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {lo}-{hi}/{size}")
        self.send_header("Content-Length", str(hi - lo + 1))
        self.end_headers()
        f.seek(lo)
        self._remaining = hi - lo + 1
        return f

    def copyfile(self, source, outputfile):
        if self._range is None:
            return super().copyfile(source, outputfile)
        n = self._remaining
        while n > 0:
            buf = source.read(min(65536, n))
            if not buf:
                break
            outputfile.write(buf)
            n -= len(buf)

ROOT  = pathlib.Path(__file__).resolve().parents[2]
FIX   = ROOT / "fixtures" / "oisst-sample"
BUILD = ROOT / "build" / "oisst-sample"
P     = json.loads((FIX / "probe.json").read_text())

CELL = "https"          # one cell suffices: the axis under test is host, not flavor


@pytest.fixture(scope="module")
def http_host():
    """Serve build/oisst-sample over HTTP on an OS-assigned port."""
    repo_dir = BUILD / f"repo-{CELL}"
    if not repo_dir.exists():
        pytest.fail(f"run `just repo {CELL}` first")

    handler = lambda *a, **kw: RangeHandler(*a, directory=str(BUILD), **kw)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]                      # port 0 -> OS assigned
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    # readiness: the socket is bound before serve_forever, but poll once anyway
    with socket.create_connection(("127.0.0.1", port), timeout=5):
        pass

    yield f"http://127.0.0.1:{port}/repo-{CELL}"

    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture(scope="module")
def repo_over_http(http_host):
    spec = P["cells"][CELL]
    return ic.Repository.open(
        ic.http_storage(http_host),
        authorize_virtual_chunk_access=ic.containers_credentials(
            {spec["ref_prefix"]: ic.credentials.HttpAccess}))


def test_metadata_over_http(repo_over_http):
    """Repo metadata + native chunks via GET-only http storage, no LIST."""
    tags = [t for t in P["tags"]]
    for t in tags:
        assert repo_over_http.lookup_tag(t)
    g = zarr.open_group(repo_over_http.readonly_session("main").store, mode="r")
    assert list(g["time"][:]) == P["time"]["raw"]        # native chunk fetch over http


@pytest.mark.network
def test_probe_over_http(repo_over_http):
    """Virtual chunk read: store host localhost, byte refs still NCEI."""
    g = zarr.open_group(repo_over_http.readonly_session("main").store, mode="r")
    raw = int(g["sst"][P["probe"]["time_index"], 0,
                       P["probe"]["iy_stored"], P["probe"]["ix"]])
    assert raw == P["probe"]["sst_packed"]


class RedirectHandler(http.server.BaseHTTPRequestHandler):
    """Verbatim shape of the icechunk docs example: name service, not byte host.
    One GET, one 302, no Range, no bytes."""
    repos: dict[str, str] = {}          # set by the fixture

    def do_GET(self):
        location = self.repos.get(self.path)
        if location is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def log_message(self, fmt, *args):
        pass                            # one-line server, keep the pytest output clean


@pytest.fixture(scope="module")
def redirect_host(http_host):
    """Name service in front of the byte host: /oisst -> RangeHandler URL."""
    handler = type("Handler", (RedirectHandler,), {"repos": {"/oisst": http_host}})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/oisst"
    server.shutdown()
    thread.join(timeout=5)


def test_redirect_to_http_target_is_consumed_by_transport(redirect_host):
    """redirect_storage requires a non-http(s) store URI in the Location
    (s3://, gs://). An http target is transparently followed by the HTTP
    client layer, so icechunk receives the terminal response and never
    sees the redirect -- hence 'must be a redirect'.

    The complementary case (s3:// Location surfaces the redirect intact:
    icechunk parses it, constructs the S3 store, and fails with 'the
    repository doesn't exist' at the target) was confirmed interactively
    2026-07-08 against a throwaway 302 server; not suite-tested because
    it exits to AWS to prove a mechanism this test already pins locally.
    """
    with pytest.raises(ic.IcechunkError, match="must be a redirect"):
        ic.Repository.open(ic.redirect_storage(redirect_host))


@pytest.fixture(scope="module")
def redirect_host_tagged(http_host):
    """Name service with the scheme-tagged Location that survives the transport."""
    target = "http+icechunk://" + http_host.removeprefix("http://")
    handler = type("Handler", (RedirectHandler,), {"repos": {"/oisst": target}})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/oisst"
    server.shutdown(); thread.join(timeout=5)


@pytest.mark.xfail(
    strict=True,
    raises=BaseException,   # PanicException derives from BaseException, not
                            # Exception, and pyo3_runtime is not a public
                            # import surface -- match the base class and let
                            # the reason string carry the specificity
    reason="icechunk redirect_storage panics stripping http+icechunk:// "
           "scheme tag (redirect.rs:218, url::set_scheme special/non-special "
           "restriction; gist shared 2026-07-08, issue TBD)",
)
def test_metadata_via_tagged_redirect(redirect_host_tagged):
    """Full chain: name service -> (http+icechunk:// tag) -> byte host -> repo.
    Note limitations: resolved backend is read-only + anonymous -- fine here,
    and virtual-chunk authorization is a separate layer passed at open."""
    repo = ic.Repository.open(ic.redirect_storage(redirect_host_tagged))
    for t in P["tags"]:
        assert repo.lookup_tag(t)
    g = zarr.open_group(repo.readonly_session("main").store, mode="r")
    assert list(g["time"][:]) == P["time"]["raw"]
