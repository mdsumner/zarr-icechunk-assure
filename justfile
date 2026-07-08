set shell := ["bash", "-cu"]

FIX   := "fixtures/oisst-sample"
BUILD := "build/oisst-sample"

# list recipes
default:
    just --list

# harvest S3 listing → sources.parquet (network; run rarely)
sources:
    Rscript R/make_sources.R

# kerchunk-parquet refs for a matrix cell (reads local mirror)
refs cell="https":
    mkdir -p {{BUILD}}
    Rscript R/make_refs.R {{cell}}

# icechunk repo, two tagged snapshots (offline build; receipt does one NCEI read)
repo cell="https":
    rm -rf -- "./{{BUILD}}/repo-{{cell}}"
    python3 py/make_repo.py {{cell}}

# promote live repo → dated immutable fixture (store-only zip)
zip cell="https":
    cd {{BUILD}}/repo-{{cell}} && zip -0 -r "../../../{{FIX}}/repo-{{cell}}-$(date +%F).zip" .

# offline test suites, both languages
test:
    Rscript -e 'testthat::test_dir("R/tests")'
    uv run --project py pytest py/tests -m "not network"

# full suites including remote value reads (NCEI https + anonymous S3)
test-network:
    Rscript -e 'testthat::test_dir("R/tests")'
    uv run --project py pytest py/tests
