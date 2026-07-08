#!/usr/bin/env python3
"""Explore the PACE OCI L3M RRS icechunk repo on source.coop.

An external exemplar for zarr-icechunk-assure: a production repo we did not
build, read as receipts. Five blocks, each prints what it measures:

  1. authority map   -- declared virtual chunk containers, commit history
  2. inventory       -- every virtual chunk location, no credentials needed
  3. grouped access  -- hierarchy addressing, native coordinate fetch
  4. the gate        -- unauthorized virtual read refused, prefix named
  5. regional gate   -- AUTHORIZED read, still refused: NASA's STS role
                        (s3-same-region-access-role) embeds an explicit deny
                        for out-of-region requests. EXPECTED TO FAIL from
                        outside us-west-2; the identical open is expected to
                        succeed on in-region compute (not yet receipted).

Blocks 1-4 need no credentials. Block 5 needs an Earthdata login (netrc entry
for urs.earthdata.nasa.gov or interactive prompt) and runs only with
--earthdata. This is an exploration script, not a test: the repo is under
someone else's control and its numbers will drift.

Findings first measured 2026-07-08 (icechunk 2.1.0):
  52,246,544 chunk refs across 1,648 source objects; chunk grid
  (1, 16, 1024, 8) inherited from source HDF5 -- refs-as-confetti, the
  opposite regime from OISST's one-chunk-per-file. Update pattern: batch
  commits with a progress cursor ("Add through file N").
"""
import sys
import time

import zarr
import icechunk as ic

URL = "https://data.source.coop/fish-pace/pace-oci/inregion/PACE_OCI_L3M_RRS"
GROUP = "daily/0p1deg"
PREFIX = "s3://ob-cumulus-prod-public/"


def block1_authority_map(repo):
    print("== 1. authority map ==")
    print(repo.config.virtual_chunk_containers)
    print("-- ancestry (most recent first) --")
    for s in repo.ancestry(branch="main"):
        print(s.written_at, s.message)


def block2_inventory(sess):
    print("== 2. inventory (no credentials) ==")
    t0 = time.perf_counter()
    locs = sess.all_virtual_chunk_locations()
    dt = time.perf_counter() - t0
    objects = {u.rsplit("/", 1)[-1] for u in locs}
    print(f"{len(locs)} chunk refs across {len(objects)} objects "
          f"({dt:.1f}s to materialize)")


def block3_grouped(sess):
    print(f"== 3. grouped access ({GROUP}) ==")
    g = zarr.open_group(sess.store, path=GROUP, mode="r")
    print(dict(g["Rrs"].attrs))
    print("shape", g["Rrs"].shape, "chunks", g["Rrs"].chunks)
    print("wavelength[:5]", g["wavelength"][:5], "(native chunk fetch over https)")
    return g


def block4_gate(g):
    print("== 4. the gate (unauthorized virtual read) ==")
    try:
        g["Rrs"][0, 0, 0, 0]
        print("UNEXPECTED: read succeeded without authorization")
    except ic.IcechunkError as e:
        # icechunk's own gate explains itself; first line suffices here
        print("GATE:", str(e).splitlines()[0].strip())


def block5_regional_gate():
    print("== 5. regional gate (authorized, out-of-region) ==")
    import earthaccess

    auth = earthaccess.login()
    c = auth.get_s3_credentials(daac="OBDAAC")   # STS triple, ~1h expiry
    repo = ic.Repository.open(
        ic.http_storage(URL),
        authorize_virtual_chunk_access=ic.containers_credentials({
            PREFIX: ic.s3_static_credentials(
                access_key_id=c["accessKeyId"],
                secret_access_key=c["secretAccessKey"],
                session_token=c["sessionToken"],
            )
        }),
    )
    g = zarr.open_group(repo.readonly_session("main").store, path=GROUP, mode="r")
    try:
        v = g["Rrs"][0, 0, 0, 0]
        print("SUCCESS (in-region compute?):", v)
    except ic.IcechunkError as e:
        # print the FULL chain: the refusing authority (AWS) puts the real
        # story (AccessDenied, role name, granule, request ids) at the leaf;
        # the wrapper's first line says only "error fetching virtual
        # reference". Never truncate a gate you did not build.
        print(str(e))


def main():
    repo = ic.Repository.open(ic.http_storage(URL))   # deliberately no auth
    block1_authority_map(repo)
    sess = repo.readonly_session("main")
    block2_inventory(sess)
    g = block3_grouped(sess)
    block4_gate(g)
    if "--earthdata" in sys.argv:
        block5_regional_gate()
    else:
        print("== 5. skipped (pass --earthdata to attempt the credentialed read) ==")


if __name__ == "__main__":
    main()
