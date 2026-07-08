## R/tests/helper-probe.R
## Sourced automatically by testthat::test_dir() before any test-*.R
## (load_helpers = TRUE default). Single authority for paths + contract.
ROOT  <- normalizePath(file.path(getwd(), "..", ".."))
FIXD  <- file.path(ROOT, "fixtures", "oisst-sample")
P     <- jsonlite::read_json(file.path(FIXD, "probe.json"), simplifyVector = TRUE)

CELLS <- c("https", "s3")   # built cells; a missing build FAILS, never shrinks

refs_path <- function(cell) file.path(ROOT, "build", "oisst-sample",
                                      sprintf("refs-%s.zarr", cell))
read_zmeta <- function(cell) {
  jsonlite::read_json(file.path(refs_path(cell), ".zmetadata"),
                      simplifyVector = FALSE)$metadata
}
skip_if_no_refs <- function(cell) testthat::skip_if_not(
  dir.exists(refs_path(cell)), sprintf("run `just refs %s` first", cell))

gdal_coherent <- function() {
  isTRUE(gdalraster::gdal_version()[4] == vapour::vapour_gdal_version()[1] |>
           sub(pattern = "GDAL ([^,]+),.*", replacement = "\\1", x = _))
}
skip_if_gdal_mixed <- function() testthat::skip_if_not(
  gdal_coherent(), "mixed GDAL versions across R bindings")
