cell <- commandArgs(trailingOnly = TRUE)[1]
if (is.na(cell)) cell <- "https"

P   <- jsonlite::read_json("fixtures/oisst-sample/probe.json", simplifyVector = TRUE)
stopifnot(cell %in% names(P$cells))
src <- arrow::read_parquet("fixtures/oisst-sample/sources.parquet")

access_root <- Sys.getenv("OISST_ACCESS_ROOT",
                          "/rdsi/PUBLIC/raad/data/www.ncei.noaa.gov/data/sea-surface-temperature-optimum-interpolation/v2.1/access/avhrr")
src <- arrow::read_parquet("fixtures/oisst-sample/sources.parquet") |>
  dplyr::mutate(
    access = file.path(access_root, source),                    # where bytes are read (machine env)
    public = paste0(P$cells[[cell]]$ref_prefix, source)         # what gets baked (contract)
  )
out <- file.path("build/oisst-sample", sprintf("refs-%s.zarr", cell))
fs::dir_create(dirname(out))

vrt <- vrtstack::vrtstack(src$access, concat = "(\\d{8})", parse_format = "%Y%m%d",
                          origin = "1978-01-01", unit = "days",
                          template = TRUE, concat_dim = "time")
readr::write_file(vrt, tf <- tempfile(fileext = ".vrt"))
blocklist::virtualize_mosaic(tf, out, sources = src)

## receipt: assert against the contract, then testify
p1 <- arrow::read_parquet(file.path(out, "sst", "refs.0.parq")) |>
  dplyr::filter(!is.na(path))
stopifnot(nrow(p1) == P$sources$n,
          all(startsWith(p1$path, P$cells[[cell]]$ref_prefix)))
cat(sprintf("OK %s: %d refs, first=%s\n", out, nrow(p1), basename(p1$path[1])))
