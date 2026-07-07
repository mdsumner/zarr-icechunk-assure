"""Read-suite for the OISST sample icechunk repo.
Every assertion is a fact from probe.json; no test writes anything.
Marks: network = fetches virtual chunks from NCEI.
"""
import json, pathlib, zipfile
import pytest
import zarr
import icechunk as ic

FIX   = pathlib.Path("fixtures/oisst-sample")
BUILD = pathlib.Path("build/oisst-sample")
P     = json.loads((FIX / "probe.json").read_text())
CELL  = "https"
PREFIX = P["cells"][CELL]["ref_prefix"]

def _storage(path):
    return ic.local_filesystem_storage(str(path))

@pytest.fixture(scope="session")
def repo_path(tmp_path_factory):
    """Prefer the live build; fall back to unzipping the newest promoted fixture."""
    live = BUILD / f"repo-{CELL}"
    if live.exists():
        return live
    z = sorted(FIX.glob(f"repo-{CELL}-*.zip"))[-1]
    out = tmp_path_factory.mktemp("repo")
    with zipfile.ZipFile(z) as f:
        f.extractall(out)
    return out

@pytest.fixture(scope="session")
def repo_auth(repo_path):
    return ic.Repository.open(_storage(repo_path),
        authorize_virtual_chunk_access=ic.containers_credentials(
            {PREFIX: getattr(ic.credentials, P["cells"][CELL]["credential"])}))

@pytest.fixture(scope="session")
def repo_noauth(repo_path):
    return ic.Repository.open(_storage(repo_path))

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
    sst = _group(repo_auth)["sst"]
    raw = int(sst[P["probe"]["time_index"], 0, P["probe"]["iy_stored"], P["probe"]["ix"]])
    assert raw == P["probe"]["sst_packed"]
    assert round(raw * P["array"]["scale_factor"], 2) == P["probe"]["sst_unpacked"]

# ---- the gate ---------------------------------------------------------------

@pytest.mark.network
def test_unauthorized_read_names_prefix(repo_noauth):
    sst = _group(repo_noauth)["sst"]
    with pytest.raises(ic.IcechunkError, match="ncei.noaa.gov"):
        sst[0, 0, P["probe"]["iy_stored"], P["probe"]["ix"]]
