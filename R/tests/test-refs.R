## R/tests/test-refs.R  -- refs store structure, offline
test_that("refs carry contract prefix and count", {
  skip_if_no_refs()
  p1 <- arrow::read_parquet(file.path(REFS, "sst", "refs.0.parq")) |>
    dplyr::filter(!is.na(path))                    # parquet padding rows
  expect_equal(nrow(p1), P$sources$n)
  expect_true(all(startsWith(p1$path, P$cells$https$ref_prefix)))
  expect_identical(p1$path, sort(p1$path))         # date order = chunk order
  expect_true(all(p1$offset >= 0 & p1$size > 0))
})

test_that("v2 codec chain matches contract", {
  skip_if_no_refs()
  za <- read_zmeta()[["sst/.zarray"]]
  expect_equal(vapply(za$filters, `[[`, "", "id"),
               P$array$codecs_v2_filters[["id"]])

  expect_equal(za$fill_value, P$array$fill_value)
})

test_that("time units defect state is fixed #14881", {
  skip_if_no_refs()
  zat <- read_zmeta()[["time/.zattrs"]]
  expect_true("units" %in% names(zat))
})
