## R/tests/test-sources.R  -- fixture integrity, fully offline
## R/tests/test-sources.R
test_that("sources fixture matches contract", {
  src <- arrow::read_parquet(file.path(FIXD, "sources.parquet"))
  expect_equal(nrow(src), P$sources$n)
  expect_false(any(duplicated(src$date)))
  expect_true(all(diff(src$date) == 1))
  expect_false(any(src$preliminary))
})
