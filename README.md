# zarr-icechunk-assure

Assurance and illustration for virtualized datasets: a small
pipeline that takes a curated file listing to a versioned Icechunk repository,
stages verified, in R and Python. 

The sample dataset is ten days of NOAA OISST v2.1 (September 1981). Small, but real
(packed int16, scale/offset, shuffle+zlib chunks, CF time, virtual byte
references into a remote archive).

This is an evolving project, there's a lot of LLM assistance. Stay tuned, reach out to me if you are interested. 

## Why

Virtualization datasets can easily have multiple authorities, at its simplest
the store can be on your website or in your local directory, but the data referenced are online S3, urls, behind auth/config. 

This repo is for: 

1. **Assurance.** R/GDAL-built references loaded into Icechunk via
   the direct store API. Traditional tools xarray, VirtualiZarr are used only 
   for verification. Every stage of the
   pipeline checks output against `fixtures/oisst-sample/probe.json`.

2. **Illustration.** The fixture demonstrates what
   tools need: metadata reads that need no credentials, value reads from
   a remote container, unauthorized reads, and we retain 
   a metadata defect repaired as a versioned commit. 

## Contract

There is a core that doesn't live here but is developing in blocklist/aad-filelist and in GDAL. 

Once we assume that core contract (a generic, managed, and growing store of array data 
byte-refs) the goal here is to project it through different types, which varies by when it binds and whether 
it can be undone. 

- **bake-time**, irreversible, the reference **flavour** (`https://` / `/my/data/` / `file://` / `s3://`) written into the refs themselves — changing it is a rebuild, hence it names the artifact.
- **deploy-time**, reversible, the store host which has the same bytes in a different container or access requirement, it never names anything.
- **open-time**, per-session, requires credentials/authorization. 
- **read-time**, per-tool, involves dialect variants (`/vsis3/` vs `s3://` vs `https://`). 


## Pipeline

```
sources.parquet ──> refs-{cell}.zarr ──> repo-{cell}/ ──> repo-{cell}-<date>.zip
   (harvest)          (R: vrtstack +       (Python:           (promoted
                       blocklist)           icechunk +          immutable
                                            zarr, direct        fixture)
                                            store API)
```

- **Step 1 — harvest** (`R/make_sources.R`): list the NOAA S3 bucket, dedup
  preliminary vs final per date, freeze the flavor-neutral listing
  (`date`, `source`, `preliminary`) as `fixtures/oisst-sample/sources.parquet`.
  Network; run rarely. The fixture is the hardcoded list, held properly.
- **Step 2 — refs** (`R/make_refs.R <cell>`): build a multidimensional VRT
  mosaic (vrtstack) from a local mirror, then a kerchunk-parquet reference
  store (blocklist) with the cell's URL flavor baked into the refs.
- **Step 3 — repo** (`py/make_repo.py <cell>`): create an Icechunk repository
  with the direct store API — no VirtualiZarr, no xarray, no fsspec.
  Coordinates are composed from the grid spec, not fetched; repo creation is
  fully offline. Two tagged snapshots are built every time:
  - `as-virtualized` — faithful to the refs as written, including a known
    defect (time `units` attribute absent);
  - `cf-repaired` — the defect fixed as a metadata-only commit, zero refs
    rewritten. The defect is kept deliberately: repairing it *is* the
    demonstration of why the Icechunk layer earns its keep over static refs.
- **Promotion** (`just zip`): the live repo is frozen into a dated,
  store-only zip under `fixtures/`. The zip is the artifact of record — it is
  what the read tests fall back to, and it is readable in place by GDAL:

  ```
  gdal mdim info /vsiicechunk/{/vsizip/fixtures/oisst-sample/repo-https-<date>.zip}/
  ```

## The matrix

The store and the byte references authenticate independently - that split is
the core Icechunk design this repo exercises. Cells are declared once in
`probe.json` and every script takes the cell as its parameter.

| cell    | refs baked as                  | container store          | credential (icechunk 2.1) | status  |
|---------|--------------------------------|--------------------------|---------------------------|---------|
| `https` | `https://www.ncei.noaa.gov/…`  | `http_store`             | `HttpAccess`              | built   |
| `file`  | `file:///rdsi/…` (machine-bound by construction) | `local_filesystem_store` | `LocalFileSystemAccess`   | planned |

The flavor is baked into the refs at **write time** (step 2); the Icechunk
container and credentials must match it at **open time**. Naming the cell in
every artifact (`refs-https.zarr`, `repo-https`) keeps that irreversible
decision visible.

## Layout

```
fixtures/oisst-sample/   committed ground truth + promoted immutables
  probe.json             the contract: every expected number, hand-written
  sources.parquet        frozen file listing (flavor-neutral)
  repo-https-<date>.zip  promoted read-fixture
build/oisst-sample/      gitignored, wholly regenerable
  refs-{cell}.zarr/      kerchunk-parquet reference store
  repo-{cell}/           live icechunk repository
R/                       harvest + refs recipes, testthat suite
py/                      repo recipe, pytest suite
justfile                 the executable README of the pipeline
```

Rule: recipes are versioned, products are regenerable, immutables are
promoted deliberately. If `git status` shows churn under `fixtures/`, the
layout has been violated.

## Running

```
just            # list recipes
just refs       # build refs-https.zarr   (needs local OISST mirror; see below)
just repo       # build repo-https        (offline; receipt does one NCEI read)
just zip        # promote to dated fixture zip
just test       # offline test suites, both languages
```

The only machine-bound configuration is the mirror location for step 2:
`OISST_ACCESS_ROOT` (defaults to the AAD raad mirror path). Without a mirror,
`just refs` is unavailable but the read suites still pass against the
promoted zip — that asymmetry is by design.

## Tests

Two suites, no shared code, one shared contract. Both read `probe.json` and
assert the same numbers through different stacks:

- **pytest** (`py/tests/`): icechunk + zarr-python. Tags present, shapes,
  native coordinates readable with *no* credentials, tag states differ
  (defect vs repair), v3 codec names, probe value via authorized open
  (marked `network`), and the gate: an unauthorized read raises with the
  container prefix named in the error.
- **testthat** (`R/tests/`): fixture integrity, ref counts and prefixes
  (padding-aware), v2 codec chain, the defect state in `.zattrs`, and GDAL
  receipts via `gdal mdim info` and a coordinate-space probe read.

The probe is defined in coordinate space (lon 199.875, lat −9.875 →
sst 27.82 unpacked / 2782 packed) with all three addressings recorded in the
contract, so GDAL's north-up view and Zarr's stored-ascending view assert the
same pixel without orientation traps.

## Known facts the fixture encodes on purpose

- kerchunk-parquet ref files are padded; rows with null `path` are format,
  not data.
- The v2 filters (`shuffle`, `zlib`) and the v3 codec names
  (`numcodecs.shuffle`, `numcodecs.zlib`) are the same bytes under two
  registries; readers should alias, not hardcode spellings.
- GDAL's Zarr V3 path does not yet decode those two names — the promoted zip
  is the minimal public repro for the upstream request (metadata and
  coordinates read fine; only the data arrays error).
- Baked `file://` refs cannot be portable. That is not a flaw of the `file`
  cell; it is one of the facts about virtualization this repo exists to
  illustrate.

## Status 

Built against icechunk 2.1.0 (format v2), zarr-python 3.x, GDAL 3.14-dev
(Icechunk driver + `/vsiicechunk`), R with vrtstack + blocklist from the
hypertidy ecosystem.
