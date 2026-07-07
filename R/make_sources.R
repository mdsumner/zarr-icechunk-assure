

root <-      "/vsis3/noaa-cdr-sea-surface-temp-optimum-interpolation-pds/data/v2.1/avhrr"
## root can be replaced with
#httproot <- "https://www.ncei.noaa.gov/data/sea-surface-temperature-optimum-interpolation/v2.1/access/avhrr"
## or with localroot
#localroot <- "/rdsi/PUBLIC/raad/data/www.ncei.noaa.gov/data/sea-surface-temperature-optimum-interpolation/v2.1/access/avhrr"
gdalraster::set_config_option("AWS_NO_SIGN_REQUEST", "YES")
f <- gdalraster::vsi_read_dir(root, recursive = TRUE)

d <- as.Date(stringr::str_extract(f, "[0-9]{8}"), "%Y%m%d")

paths <- tibble::tibble(date = d, source = f)

## drop any preliminary that also have a final
paths <- paths |>
  dplyr::mutate(preliminary = grepl("preliminary", source)) |>
  dplyr::arrange(date, preliminary) |>
  dplyr::distinct(date, .keep_all = TRUE)

## above we sanitize a full list of no overlapping files, even though we only use a subset for now
src <- paths[1:10, ]

src |> dplyr::select(date, source, preliminary) |>
  arrow::write_parquet("fixtures/oisst-sample/sources.parquet")

# vrt <- vrtstack::vrtstack(src$access, concat = "(\\d{8})", parse_format = "%Y%m%d",
#                           origin = "1978-01-01", unit = "days",   # must match the template
#                           template = TRUE, concat_dim = "time")
#
# ## write that xml blob to a tempfile
# readr::write_file(vrt, tf <- tempfile(fileext = "vrt"))
# ## the kerchunk zarr here gets made from local access files, and is intended for bare https:// read downstream
# blocklist::virtualize_mosaic(tf, "oisst-sample.zarr", sources = src)
