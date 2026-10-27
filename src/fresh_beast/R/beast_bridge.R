#!/usr/bin/env Rscript

# Thin, auditable bridge to the reference Rbeast implementation.
#
# Input : CSV with first column `time` (decimal years, regular 16-day grid)
#         and one column per pixel id.
# Output: two CSVs, `--summary` and `--long`, with the BEAST trend
#         changepoint probabilities and diagnostics.
#
# This script deliberately does not add a disturbance classifier. It exposes
# BEAST outputs unchanged except for the time-axis interpretation.

suppressPackageStartupMessages(library(Rbeast))

args <- commandArgs(trailingOnly = TRUE)
get_arg <- function(name) {
  index <- match(name, args)
  if (is.na(index) || index == length(args)) {
    stop(paste("missing argument", name))
  }
  args[[index + 1L]]
}

input <- get_arg("--input")
summary_path <- get_arg("--summary")
long_path <- get_arg("--long")
min_valid_arg <- get_arg("--min-valid")
min_valid <- as.integer(min_valid_arg)

data <- read.csv(input, check.names = FALSE)
time <- as.numeric(data[[1]])
if (length(time) < 10) {
  stop("BEAST needs at least 10 time steps")
}
if (any(!is.finite(time))) {
  stop("time column contains non-finite values")
}
time_diff <- diff(time)
if (length(time_diff) > 1 && max(abs(time_diff - median(time_diff))) > 1e-6) {
  stop("time must be a regular grid")
}
deltat <- median(time_diff)
if (!is.finite(deltat) || deltat <= 0) {
  deltat <- 16 / 365.25
}

# Rbeast defaults are retained here because Brown et al. (2025) do not report
# a replacement MCMC prior. `season` and the time axis are the choices needed
# to make the published 16-day, annual-cycle design explicit.
beast_args <- list(
  start = time[[1]],
  deltat = deltat,
  period = 1.0,
  season = "harmonic",
  quiet = TRUE,
  print.progress = FALSE,
  print.warning = FALSE
)

summary_rows <- list()
long_rows <- list()
pixel_ids <- names(data)[-1]

for (pixel_id in pixel_ids) {
  y <- as.numeric(data[[pixel_id]])
  valid <- is.finite(y)
  n_valid <- sum(valid)
  if (n_valid < min_valid) {
    summary_rows[[pixel_id]] <- data.frame(
      pixel_id = pixel_id,
      status = "insufficient_observations",
      n_valid = n_valid,
      ncp_median = NA_real_,
      r2 = NA_real_,
      rmse = NA_real_,
      max_neg_cp = NA_real_,
      max_neg_time = NA_real_,
      max_neg_year = NA_integer_,
      max_neg_change = NA_real_,
      stringsAsFactors = FALSE
    )
    next
  }

  fit <- tryCatch(
    do.call(beast, c(list(y = y), beast_args)),
    error = function(error) error
  )
  if (inherits(fit, "error")) {
    summary_rows[[pixel_id]] <- data.frame(
      pixel_id = pixel_id,
      status = paste("beast_error:", conditionMessage(fit)),
      n_valid = n_valid,
      ncp_median = NA_real_,
      r2 = NA_real_,
      rmse = NA_real_,
      max_neg_cp = NA_real_,
      max_neg_time = NA_real_,
      max_neg_year = NA_integer_,
      max_neg_change = NA_real_,
      stringsAsFactors = FALSE
    )
    next
  }

  trend <- fit$trend
  cp_prob <- as.numeric(trend$cpOccPr)
  neg_prob <- as.numeric(trend$neg_cpOccPr)
  dec_prob <- as.numeric(trend$dec_cpOccPr)
  inc_prob <- as.numeric(trend$inc_cpOccPr)
  trend_mean <- as.numeric(trend$Y)
  slope <- as.numeric(trend$slp)
  slope_sd <- as.numeric(trend$slpSD)

  max_index <- which.max(neg_prob)
  max_neg_cp <- if (length(max_index) == 0) NA_real_ else neg_prob[[max_index]]
  max_neg_time <- if (length(max_index) == 0) NA_real_ else time[[max_index]]
  max_neg_year <- if (is.na(max_neg_time)) NA_integer_ else as.integer(floor(max_neg_time))
  max_neg_change <- NA_real_
  if (!is.null(trend$neg_cpAbruptChange) && length(trend$neg_cpAbruptChange) > 0) {
    # The first negative changepoint is the dominant step when BEAST reports
    # more than one candidate; keep it only as a diagnostic, not as severity.
    max_neg_change <- as.numeric(trend$neg_cpAbruptChange[[1]])
  }

  summary_rows[[pixel_id]] <- data.frame(
    pixel_id = pixel_id,
    status = "ok",
    n_valid = n_valid,
    ncp_median = as.numeric(trend$ncp_median),
    r2 = as.numeric(fit$R2),
    rmse = as.numeric(fit$RMSE),
    max_neg_cp = max_neg_cp,
    max_neg_time = max_neg_time,
    max_neg_year = max_neg_year,
    max_neg_change = max_neg_change,
    stringsAsFactors = FALSE
  )

  long_rows[[pixel_id]] <- data.frame(
    pixel_id = pixel_id,
    time = time,
    cp_occ_pr = cp_prob,
    neg_cp_occ_pr = neg_prob,
    dec_cp_occ_pr = dec_prob,
    inc_cp_occ_pr = inc_prob,
    trend = trend_mean,
    slope = slope,
    slope_sd = slope_sd,
    stringsAsFactors = FALSE
  )
}

summary_table <- do.call(rbind, summary_rows)
write.csv(summary_table, summary_path, row.names = FALSE, na = "")

if (length(long_rows) > 0) {
  long_table <- do.call(rbind, long_rows)
  write.csv(long_table, long_path, row.names = FALSE, na = "")
} else {
  write.csv(
    data.frame(
      pixel_id = character(),
      time = numeric(),
      cp_occ_pr = numeric(),
      neg_cp_occ_pr = numeric(),
      dec_cp_occ_pr = numeric(),
      inc_cp_occ_pr = numeric(),
      trend = numeric(),
      slope = numeric(),
      slope_sd = numeric()
    ),
    long_path,
    row.names = FALSE,
    na = ""
  )
}
