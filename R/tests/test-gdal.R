for (cell in CELLS) {
  test_that(sprintf("gdal mdim sees the mosaic structure [%s]", cell), {
    skip_if_no_refs(cell)
    info <- system2("gdal", c("mdim", "info",
                              sprintf("/vsikerchunk_parquet_ref/{%s}", refs_path(cell))),
                    stdout = TRUE, stderr = FALSE)
    expect_true(any(grepl("\\[10, 1, 720, 1440\\]", info)))
  })

  test_that(sprintf("probe value via GDAL [%s]", cell), {
    skip_if_no_refs(cell); skip_if_offline(); skip_on_ci()
    withr::local_envvar(AWS_NO_SIGN_REQUEST = "YES")   # env, not set_config_option
    d <- vapour::gdal_raster_data(
      sprintf('ZARR:"/vsikerchunk_parquet_ref/{%s}":/sst', refs_path(cell)),
      bands = 1L)
    cellidx <- vaster::cell_from_xy(P$grid$dim, P$grid$extent,
                                    cbind(P$probe$lon, P$probe$lat))
    expect_equal(d[[1]][cellidx], P$probe$sst_unpacked, tolerance = 1e-8)
  })
}
