## rung 1


#root <-      "/vsis3/noaa-cdr-sea-surface-temp-optimum-interpolation-pds/data/v2.1/avhrr"
## root can be replaced with
httproot <- "https://www.ncei.noaa.gov/data/sea-surface-temperature-optimum-interpolation/v2.1/access/avhrr"
## or with localroot
localroot <- "/rdsi/PUBLIC/raad/data/www.ncei.noaa.gov/data/sea-surface-temperature-optimum-interpolation/v2.1/access/avhrr"

src <- arrow::read_parquet("oisst-sample-sources.parquet")
access <- file.path(localroot, src$source)   # rung 1-3
public <- file.path(httproot,  src$source)


vrt <- vrtstack::vrtstack(access, concat = "(\\d{8})", parse_format = "%Y%m%d",
                          origin = "1978-01-01", unit = "days",
                          template = TRUE, concat_dim = "time")
readr::write_file(vrt, tf <- tempfile(fileext = ".vrt"))

system(sprintf("gdal mdim info %s", tf))
# ...
# /sst         Int16  Celsius  [10, 1, 720, 1440]  [1, 1, 720, 1440]
#
# Arrays:
#
#   - /time:
#   Dimensions:  (/time)
# Shape:       [10]
# Type:        Float64
# Unit:        days since 1978-01-01 12:00:00
#
# Attributes:
#   Name      Type            Value
# ---------  ------  ------------------------
#   long_name  String  "Center time of the day"
# ...


terra::rast(tf, "sst")[[1]] * 1
# class       : SpatRaster
# size        : 720, 1440, 1  (nrow, ncol, nlyr)
# resolution  : 0.25, 0.25  (x, y)
# extent      : 0, 360, -90, 90  (xmin, xmax, ymin, ymax)
# coord. ref. : lon/lat WGS 84 (CRS84) (OGC:CRS84)
# source(s)   : memory
# varname     : sst (Daily sea surface temperature)
# name        : sst_zlev=0_1
# min value   :         -1.8
# max value   :    33.739999
# depth       : 0
# time (days) : 1981-09-01

terra::rast(tf, "sst")[[1]][400, 800]
# sst_zlev=0_1
# 1        27.82


## rung 2


src <- arrow::read_parquet("oisst-sample-sources.parquet")
src$public <- file.path(httproot, src$source)
src$access <- sprintf("%s/%s", localroot, src$source)
blocklist::virtualize_mosaic(tf, "oisst-sample.zarr", sources = src)


arrow::read_parquet("oisst-sample.zarr/anom/refs.0.parq")[1, ]
# # A tibble: 1 × 4
# path                                                                                 offset   size   raw
# <chr>                                                                                 <int>  <int> <arr>
#   1 https://www.ncei.noaa.gov/data/sea-surface-temperature-optimum-interpolation/v2.1/a…  47747 684063

reticulate::use_python("/usr/bin/python3")
xarray <- reticulate::import("xarray")
# ds <- xarray$open_dataset("ZARR:oisst-sample.zarr/", engine = "gdalxarray")
# ARROW: Memory pool: bytes_allocated = 0
# ARROW: Memory pool: max_memory = 2944320
# GDAL: GDALClose(oisst-sample.zarr/sst/refs.0.parq, this=0x5eff70871a70)
# ARROW: Memory pool: bytes_allocated = 0
# ARROW: Memory pool: max_memory = 2941504
# GDAL: GDALClose(oisst-sample.zarr/zlev/refs.0.parq, this=0x5eff72fef180)
# ARROW: Memory pool: bytes_allocated = 0
# ARROW: Memory pool: max_memory = 2941632
# GDAL: GDALClose(oisst-sample.zarr/time/refs.0.parq, this=0x5eff710ff4f0)
# ARROW: Memory pool: bytes_allocated = 0
# ARROW: Memory pool: max_memory = 2964416
# GDAL: GDALClose(oisst-sample.zarr/lon/refs.0.parq, this=0x5eff78b71da0)
# ARROW: Memory pool: bytes_allocated = 0
# ARROW: Memory pool: max_memory = 2952896
# GDAL: GDALClose(oisst-sample.zarr/lat/refs.0.parq, this=0x5eff70cd8c30)
# GDAL: GDALOpen(ZARR:oisst-sample.zarr/, this=0x5eff7e3f2890) succeeds as Zarr.
# PARQUET: Compression (of first column): snappy
# GDAL: GDALOpen(oisst-sample.zarr/lat/refs.0.parq, this=0x5eff72fef180) succeeds as Parquet.
# PARQUET: Compression (of first column): snappy
# GDAL: GDALOpen(oisst-sample.zarr/lon/refs.0.parq, this=0x5eff70cd8c30) succeeds as Parquet.
# PARQUET: Compression (of first column): snappy
# GDAL: GDALOpen(oisst-sample.zarr/time/refs.0.parq, this=0x5eff70d2a0a0) succeeds as Parquet.
# PARQUET: Compression (of first column): snappy
# GDAL: GDALOpen(oisst-sample.zarr/zlev/refs.0.parq, this=0x5eff78b71da0) succeeds as Parquet.
ds$isel(lat = 399L, lon = 799L, time = 0L)$sst$values
#PARQUET: Compression (of first column): snappy
#GDAL: GDALOpen(oisst-sample.zarr/sst/refs.0.parq, this=0x5eff710ff4f0) succeeds as Parquet.
#[1] 27.92
ds$isel(lat = 399L, lon = 799L, time = 9L)$sst$values
#[1] 27.21

terra::rast("ZARR:oisst-sample.zarr", "sst")[[1]][400, 800]
# sst_zlev=0_1
# 1        27.82

system(sprintf("gdal mdim info %s --array time --detailed", "ZARR:oisst-sample.zarr"))
# Arrays:
#
#   - /time:
#   Dimensions:  (/time)
# Shape:       [10]
# Chunk size:  [10]
# Type:        Float64
#
# Attributes:
#   Name      Type                Value
# ---------  ------  --------------------------------
#   long_name  String  "Center time of the day"
# units      String  "days since 1978-01-01 12:00:00"
#
# Values:
#   [1339, 1340, 1341, 1342, 1343, 1344, 1345, 1346, 1347, 1348]

system(sprintf("gdal mdim info %s", "ZARR:oisst-sample.zarr"))
# ...
# /sst:
#   Dimensions:    (/time, /zlev, /lat, /lon)
# Shape:         [10, 1, 720, 1440]
# Chunk size:    [1, 1, 720, 1440]
# Type:          Int16
# Unit:          Celsius
# Nodata value:  -999
#
# Attributes:
#   Name     Type   Value
# ----------  -----  -----
#   _FillValue  Int32   -999
#
# Structural metadata:
#   FILTERS  [ { "id": "shuffle", "elementsize": 2 }, { "id": "zlib", "level": 1 } ]
#
# - /time:
#   Dimensions:  (/time)
# Shape:       [10]
# Chunk size:  [10]
# Type:        Float64
#
# Attributes:
#   Name      Type                Value
# ---------  ------  --------------------------------
#   long_name  String  "Center time of the day"
# units      String  "days since 1978-01-01 12:00:00"
# ...
#


