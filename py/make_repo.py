#!/usr/bin/env python3
"""OISST sample icechunk repo from blocklist kerchunk-parquet refs.
Direct Store API -- no VirtualiZarr, no xarray, no fsspec.
Two tagged snapshots: as-virtualized (units defect preserved), cf-repaired.
Usage: make_repo.py [cell]   (cell = key of probe.json "cells", default https)
"""
import json, sys, pathlib
import numpy as np
import pyarrow.parquet as pq
import zarr
import icechunk as ic
from zarr.codecs.numcodecs import Shuffle, Zlib

FIX  = pathlib.Path("fixtures/oisst-sample")
BUILD = pathlib.Path("build/oisst-sample") 
cell = sys.argv[1] if len(sys.argv) > 1 else "https"

P        = json.loads((FIX / "probe.json").read_text())
if cell not in P["cells"]:
    sys.exit(f"unknown cell {cell!r}; probe.json defines: {', '.join(P['cells'])}")
cellspec = P["cells"][cell]
prefix   = cellspec["ref_prefix"]
refs = BUILD / f"refs-{cell}.zarr"
repo_dir = BUILD / f"repo-{cell}"

N        = P["sources"]["n"]
NT, NZ, NY, NX = P["array"]["shape"]
DIMS     = ("time", "zlev", "lat", "lon")

# -- cell dispatch: contract strings -> icechunk objects ---------------------
# Store configs and credentials are constructed per cell. Both tables take
# the cellspec uniformly so a new cell is a new row, not a refactor.
STORES = {
    "http_store": lambda spec: ic.http_store(),
    "local_filesystem_store": lambda spec: ic.local_filesystem_store(
        spec["ref_prefix"].removeprefix("file://")),
    # FLAGGED: check s3_store signature -- region kwarg assumed
    "s3_store": lambda spec: ic.s3_store(region=spec["region"]),
}
CREDS = {
    # sentinels are attributes; anonymous s3 is a constructor call --
    # the tables make both uniform behind a zero-arg call
    "HttpAccess": lambda: ic.credentials.HttpAccess,
    "LocalFileSystemAccess": lambda: ic.credentials.LocalFileSystemAccess,
    # FLAGGED: check exact spelling -- s3_anonymous_credentials assumed
    "s3_anonymous": lambda: ic.s3_anonymous_credentials(),
}

if cellspec["store_config"] not in STORES:
    sys.exit(f"no store factory for {cellspec['store_config']!r}; "
             f"known: {', '.join(STORES)}")
if cellspec["credential"] not in CREDS:
    sys.exit(f"no credential factory for {cellspec['credential']!r}; "
             f"known: {', '.join(CREDS)}")

store_cfg = STORES[cellspec["store_config"]](cellspec)
cred      = CREDS[cellspec["credential"]]()
config = ic.RepositoryConfig.default()
config.set_virtual_chunk_container(ic.VirtualChunkContainer(prefix, store_cfg))
creds = ic.containers_credentials({prefix: cred})
repo = ic.Repository.create(ic.local_filesystem_storage(repo_dir),
                            config, authorize_virtual_chunk_access=creds)
session = repo.writable_session("main")
root = zarr.group(store=session.store)

# -- native coordinates, composed from the grid spec (not fetched) ---------
x0, x1, y0, y1 = P["grid"]["extent"]
coords = {
    "time": (np.asarray(P["time"]["raw"], "f8"),
             {"long_name": "Center time of the day"}),   # units deliberately absent
    "zlev": (np.array([0.0]), {"units": "meters", "positive": "down"}),
    "lat":  (y0 + (np.arange(NY) + 0.5) * (y1 - y0) / NY, {"units": "degrees_north"}),
    "lon":  (x0 + (np.arange(NX) + 0.5) * (x1 - x0) / NX, {"units": "degrees_east"}),
}
for name, (vals, attrs) in coords.items():
    # FLAGGED: create_array(dimension_names=, attributes=) is zarr-python 3.x
    a = root.create_array(name, shape=vals.shape, dtype=vals.dtype,
                          dimension_names=(name,), attributes=attrs)
    a[:] = vals

# -- virtual data arrays ----------------------------------------------------
for v in P["variables"]:

    root.create_array(v, shape=(NT, NZ, NY, NX), chunks=(1, 1, NY, NX),
        dtype=P["array"]["dtype"], fill_value=P["array"]["fill_value"],
        # FLAGGED: confirm emitted zarr.json matches probe.json codecs_v3
        compressors=[Shuffle(elementsize=2), Zlib(level=1)],
        dimension_names=DIMS,
        attributes={"scale_factor": P["array"]["scale_factor"],
                    "add_offset": P["array"]["add_offset"],
                    "_FillValue": P["array"]["fill_value"]})
    tb = [r for r in pq.read_table(refs / v / "refs.0.parq").to_pylist()
          if r["path"] is not None]                       # parquet padding rows
    assert len(tb) == N, (v, len(tb))
    assert all(r["path"].startswith(prefix) for r in tb), v
    assert [r["path"] for r in tb] == sorted(r["path"] for r in tb)  # date order = chunk order
    # FLAGGED: check path form (leading slash?) and kwarg names
    session.store.set_virtual_refs(v, [
        ic.VirtualChunkSpec(index=[i, 0, 0, 0], location=r["path"],
                            offset=r["offset"], length=r["size"])
        for i, r in enumerate(tb)], validate_containers=True)

s1 = session.commit(f"OISST 1981-09-01..10: virtual refs, cell={cell} (units defect preserved)")
repo.create_tag("as-virtualized", snapshot_id=s1)

# -- the repair, as part of the recipe --------------------------------------
session = repo.writable_session("main")
g = zarr.open_group(session.store, mode="a")
g["time"].attrs["units"]    = P["time"]["units_correct"]
g["time"].attrs["calendar"] = P["time"]["calendar"]
s2 = session.commit("Add CF time units (metadata-only repair of as-virtualized)")
repo.create_tag("cf-repaired", snapshot_id=s2)

# -- receipt: probe via pure zarr + index arithmetic -------------------------
ix = int((P["probe"]["lon"] - x0) / ((x1 - x0) / NX))
iy = int((P["probe"]["lat"] - y0) / ((y1 - y0) / NY))
assert (ix, iy) == (P["probe"]["ix"], P["probe"]["iy_stored"]), (ix, iy)
sst = zarr.open_group(repo.readonly_session("main").store, mode = "r")["sst"]
raw = int(sst[0, 0, iy, ix])
assert raw == P["probe"]["sst_packed"], raw
assert round(raw * P["array"]["scale_factor"], 2) == P["probe"]["sst_unpacked"]
print(f"OK {repo_dir}: tags={P['tags']}  probe[{iy},{ix}]={raw} "
      f"({raw * P['array']['scale_factor']:.2f})  {s1=} {s2=}")
