## R/tests/helper-probe.R
## Sourced automatically by testthat::test_dir() before any test-*.R
## (load_helpers = TRUE default). Single authority for paths + contract.
stopifnot(packageVersion("testthat") >= "3.0.0")

ROOT <- normalizePath(file.path(testthat::test_path(), "..", ".."))
FIXD <- file.path(ROOT, "fixtures", "oisst-sample")
REFS <- file.path(ROOT, "build", "oisst-sample", "refs-https.zarr")

P <- jsonlite::read_json(file.path(FIXD, "probe.json"), simplifyVector = TRUE)

skip_if_no_refs <- function() {
  testthat::skip_if_not(dir.exists(REFS), "run `just refs` first")
}


read_zmeta <- function() {
  jsonlite::read_json(file.path(REFS, ".zmetadata"), simplifyVector = FALSE)$metadata
}
