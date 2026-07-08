"""Read-suite for the OISST sample icechunk repo.
Every assertion is a fact from probe.json; no test writes anything.
Marks: network = fetches virtual chunks from NCEI.
"""

import json, pathlib, re, zipfile
import pytest
import zarr
import icechunk as ic

ROOT  = pathlib.Path(__file__).resolve().parents[2]
FIX   = ROOT / "fixtures" / "oisst-sample"
BUILD = ROOT / "build" / "oisst-sample"
P     = json.loads((FIX / "probe.json").read_text())

CELLS = ["https", "s3", "file"]          # explicit: a missing build FAILS, never silently shrinks
MIRROR = pathlib.Path("/rdsi/PUBLIC/raad")   # file cell is machine-bound (probe.json note)
CREDS = {
    "HttpAccess": lambda: ic.credentials.HttpAccess,
    "LocalFileSystemAccess": lambda: ic.credentials.LocalFileSystemAccess,
    "s3_anonymous": lambda: ic.s3_anonymous_credentials(),
}


@pytest.fixture(scope="session", params=CELLS)
def cell(request):
    return request.param

@pytest.fixture(scope="session")
def cellspec(cell):
    return P["cells"][cell]


@pytest.fixture(scope="session")
def repo_path(cell, tmp_path_factory):
    live = BUILD / f"repo-{cell}"
    if live.exists():
        return live
    zips = sorted(FIX.glob(f"repo-{cell}-*.zip"))
    if not zips:
        if cell == "file":
            # never promoted, by contract -- absence of a build on a
            # mirror-less machine is the designed state, not a failure
            pytest.skip("file cell: no live build and no zip by design "
                        "(machine-bound; see probe.json note)")
        pytest.fail(f"no live build and no promoted zip for cell {cell!r}")
    out = tmp_path_factory.mktemp(f"repo-{cell}")
    with zipfile.ZipFile(zips[-1]) as f:
        f.extractall(out)
    return out
  

@pytest.fixture(scope="session")
def repo_auth(repo_path, cellspec):
    return ic.Repository.open(
        ic.local_filesystem_storage(str(repo_path)),
        authorize_virtual_chunk_access=ic.containers_credentials(
            {cellspec["ref_prefix"]: CREDS[cellspec["credential"]]()}))

@pytest.fixture(scope="session")
def repo_noauth(repo_path):
    return ic.Repository.open(ic.local_filesystem_storage(str(repo_path)))
def _group(repo, **kw):
    """Read-only group at a repo reference; defaults to tip of main."""
    if not kw:
        kw = {"branch": "main"}
    return zarr.open_group(repo.readonly_session(**kw).store, mode="r")

# ---- metadata layer: no credentials, no network ---------------------------

def test_tags_present(repo_noauth):
    for t in P["tags"]:
        assert repo_noauth.lookup_tag(t)          # FLAGGED: or repo.tags() listing

def test_shape_and_chunks(repo_noauth):
    g = _group(repo_noauth)
    for v in P["variables"]:
        assert list(g[v].shape)  == P["array"]["shape"]
        assert list(g[v].chunks) == P["array"]["chunks"]

def test_native_coords_no_auth(repo_noauth):
    g = _group(repo_noauth)
    assert list(g["time"][:]) == P["time"]["raw"]
    assert g["lat"].attrs["units"] == "degrees_north"

def test_tag_states_differ(repo_noauth):
    before = _group(repo_noauth, tag="as-virtualized")   # FLAGGED: readonly_session kwarg form
    after  = _group(repo_noauth, tag="cf-repaired")
    assert "units" not in dict(before["time"].attrs)
    assert after["time"].attrs["units"] == P["time"]["units_correct"]

def test_codec_names(repo_noauth):
    meta = _group(repo_noauth)["sst"].metadata.to_dict()
    names = [c["name"] for c in meta["codecs"]]
    assert names == P["array"]["codecs_v3"]

# ---- value layer: authorized, network ---------------------------------------

@pytest.mark.network
def test_probe_value(repo_auth):
    if cell == "file" and not MIRROR.exists():
     pytest.skip("file cell virtual reads need the /rdsi mirror")
     sst = _group(repo_auth)["sst"]
     raw = int(sst[P["probe"]["time_index"], 0, P["probe"]["iy_stored"], P["probe"]["ix"]])
     assert raw == P["probe"]["sst_packed"]
     assert round(raw * P["array"]["scale_factor"], 2) == P["probe"]["sst_unpacked"]

# ---- the gate ---------------------------------------------------------------

@pytest.mark.network
def test_unauthorized_read_names_prefix(repo_noauth, cellspec):
    sst = _group(repo_noauth)["sst"]
    with pytest.raises(ic.IcechunkError, match=re.escape(cellspec["ref_prefix"])):
        sst[0, 0, P["probe"]["iy_stored"], P["probe"]["ix"]]

@pytest.mark.parametrize("cell", CELLS)
def test_refs_time_decodes_in_xarray(cell):
    xr = pytest.importorskip("xarray")
    refs = BUILD / f"refs-{cell}.zarr"
    print(refs)
    if not refs.exists():
        pytest.fail(f"run `just refs {cell}` first")
    ds = xr.open_dataset(str(refs), engine="kerchunk")
    assert str(ds.time.values[0]).startswith("1981-09-01T12")

@pytest.mark.network
def test_authorization_is_per_container():
    """Authorize the FILE container, read from the HTTPS repo: the refusal
    must name the https prefix. Proves auth is per-container identity, not
    a boolean. Opens repo-https inline (deliberately mismatched with the
    fixtures, whose job is keeping cell and credentials aligned)."""
    repo = ic.Repository.open(
        ic.local_filesystem_storage(str(BUILD / "repo-https")),
        authorize_virtual_chunk_access=ic.containers_credentials(
            {P["cells"]["file"]["ref_prefix"]: ic.credentials.LocalFileSystemAccess}))
    sst = zarr.open_group(repo.readonly_session("main").store, mode="r")["sst"]
    with pytest.raises(ic.IcechunkError, match=re.escape(P["cells"]["https"]["ref_prefix"])):
        sst[0, 0, P["probe"]["iy_stored"], P["probe"]["ix"]]
