## R/tests/test-gdal.R  -- GDAL as third verifier; value test needs network
test_that("gdal mdim sees the mosaic structure", {
  skip_if_no_refs()
  info <- system2("gdal", c("mdim", "info", sprintf('ZARR:"%s"', REFS)),
                  stdout = TRUE, stderr = FALSE)
  expect_true(any(grepl("\\[10, 1, 720, 1440\\]", info)))
  expect_true(any(grepl("Int16", info)))
})

test_that("probe value via GDAL https read", {
  skip_if_no_refs(); skip_if_offline(); skip_on_ci()
  d <- vapour::gdal_raster_data(sprintf('ZARR:"%s":/sst', REFS), bands = 1L)
  cell <- vaster::cell_from_xy(P$grid$dim, P$grid$extent,
                               cbind(P$probe$lon, P$probe$lat))
  expect_equal(d[[1]][cell], P$probe$sst_unpacked, tolerance = 1e-8)
})
