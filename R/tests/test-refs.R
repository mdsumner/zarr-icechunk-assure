for (cell in CELLS) {
  test_that(sprintf("refs carry contract prefix and count [%s]", cell), {
    skip_if_no_refs(cell)
    p1 <- arrow::read_parquet(file.path(refs_path(cell), "sst", "refs.0.parq")) |>
      dplyr::filter(!is.na(path))
    expect_equal(nrow(p1), P$sources$n)
    expect_true(all(startsWith(p1$path, P$cells[[cell]]$ref_prefix)))
    expect_identical(p1$path, sort(p1$path))
    expect_true(all(p1$offset >= 0 & p1$size > 0))
  })

  test_that(sprintf("v2 codec chain matches contract [%s]", cell), {
    skip_if_no_refs(cell)
    za <- read_zmeta(cell)[["sst/.zarray"]]
    expect_equal(vapply(za$filters, `[[`, "", "id"),
                 P$array$codecs_v2_filters[["id"]])
    expect_equal(za$fill_value, P$array$fill_value)
  })

  test_that(sprintf("refs carry time units (post GDAL #14881) [%s]", cell), {
    skip_if_no_refs(cell)
    expect_equal(read_zmeta(cell)[["time/.zattrs"]]$units, P$time$units_correct)
  })

  test_that(sprintf("attr boxing: scalars bare, spec-arrays boxed [%s]", cell), {
    skip_if_no_refs(cell)
    zm <- read_zmeta(cell)
    ## scalars unboxed
    expect_type(zm[["time/.zattrs"]]$units, "character")
    ## spec arrays boxed, even at length 1
    expect_true(is.list(zm[["time/.zattrs"]][["_ARRAY_DIMENSIONS"]]))
    expect_true(is.list(zm[["zlev/.zarray"]]$shape))
    expect_length(zm[["time/.zattrs"]][["_ARRAY_DIMENSIONS"]], 1L)
  })
}
