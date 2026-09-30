# =============================================================================
# make_tables.R
#
# Produces the four LaTeX tables of summary statistics under
# <project>/analysis/output/:
#   table 1: per-municipality x k        -> mun_ks/output_<muni>.tex
#   table 2: per-municipality at k = 90  -> mun_sum/output_mun_summary.tex
#   table 3: aggregated x k              -> sum_k/output_sum_k.tex
#   table 4: aggregated at k = 90        -> sum/output_sum.tex
#
# Reads per-municipality CSVs from <project>/build/output/loop_results/.
# Skips silently if those CSVs are absent (e.g., when masterfile is in
# basecapacity-loop mode and only writes lite-mode CSVs to a different
# folder).
# =============================================================================

# Individual packages rather than library(tidyverse): the meta-package is a
# heavy extra dependency and is not what the rest of this repository declares.
# purrr is needed for map_dfr(), stringr is not used directly but tidyr's
# pivot helpers below expect it to be installed.
suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tidyr)
  library(purrr)
})

script_dir <- tryCatch(
  dirname(rstudioapi::getSourceEditorContext()$path),
  error = function(e) {
    args <- commandArgs(trailingOnly = FALSE)
    file_arg <- grep("^--file=", args, value = TRUE)
    if (length(file_arg)) dirname(normalizePath(sub("^--file=", "", file_arg)))
    else getwd()
  }
)
project_root <- dirname(dirname(script_dir))
data_dir <- file.path(project_root, "build", "output", "loop_results")
out_dir  <- file.path(project_root, "analysis", "output")

municipalities <- c("Linköping", "Malmö", "Nacka", "Norrköping", "Uppsala", "Växjö")

# ---- Early-exit: nothing to do if the per-muni CSVs aren't present ---------
if (!dir.exists(data_dir)) {
  message("[make_tables] ", data_dir, " not found -- skipping table generation.")
  quit(status = 0)
}
sample_path <- file.path(data_dir,
                         paste0("summary_stats_DA_", municipalities[1], ".csv"))
if (!file.exists(sample_path)) {
  message("[make_tables] no summary_stats_*.csv in ", data_dir,
          " -- skipping table generation.")
  quit(status = 0)
}

# Academic-year ranges shown in the Municipality column of Table 2.
# Mirrors the per-municipality lists in
# build/code/functions/main_helper.py:get_years() — keep in sync.
muni_year_range <- c(
  "Linköping"  = "2020--2025",
  "Malmö"      = "2020--2025",
  "Nacka"      = "2021--2025",
  "Norrköping" = "2022--2025",
  "Uppsala"    = "2021--2026",
  "Växjö"      = "2023--2025"
)

# ---------------------------------------------------------------------------
# Load data: DA, EADAM, TTC (in that display order)
# ---------------------------------------------------------------------------
load_muni <- function(algo, muni) {
  path <- file.path(data_dir, paste0("summary_stats_", algo, "_", muni, ".csv"))
  read_csv(path, show_col_types = FALSE) %>% mutate(algo = algo, municipality = muni)
}

df <- bind_rows(
  map_dfr(municipalities, ~load_muni("DA",    .x)),
  map_dfr(municipalities, ~load_muni("EADAM", .x)),
  map_dfr(municipalities, ~load_muni("TTC",   .x))
)

# ---------------------------------------------------------------------------
# Helper: format value with std below
# ---------------------------------------------------------------------------
fmt_val <- function(mean_val, std_val, digits = 2) {
  paste0(formatC(round(mean_val, digits), format = "f", digits = digits))
}
fmt_std <- function(std_val, digits = 2) {
  paste0("(", formatC(round(std_val, digits), format = "f", digits = digits), ")")
}

# ---------------------------------------------------------------------------
# Helper: law of total variance across municipalities
# ---------------------------------------------------------------------------
total_variance <- function(means, stds, weights) {
  N <- sum(weights)
  grand_mean <- sum(weights * means) / N
  within_var <- sum(weights * stds^2) / N
  between_var <- sum(weights * (means - grand_mean)^2) / N
  sqrt(within_var + between_var)
}

# ---------------------------------------------------------------------------
# Helper: aggregate stats across municipalities for a given algo and k
# ---------------------------------------------------------------------------
aggregate_stats <- function(data, algo_val, k_val) {
  sub <- data %>% filter(algo == algo_val, k == k_val)
  n <- sub$total_nr_students_mean
  N <- sum(n)

  nr_switch     <- sum(sub$nr_switchers_mean)
  nr_first      <- sum(sub$nr_first_preference_switchers_mean)
  tot_wait      <- sum(sub$total_waiting_time_mean)
  tot_wait_sw   <- sum(sub$total_waiting_time_switchers_mean)

  pct_switch    <- nr_switch / N * 100
  pct_first     <- nr_first / N * 100
  avg_wait      <- tot_wait / N
  avg_wait_sw   <- if (nr_switch > 0) tot_wait_sw / nr_switch else 0

  pct_switch_std <- total_variance(sub$percent_switchers_mean, sub$percent_switchers_std, n)
  pct_first_std  <- total_variance(sub$percent_first_preference_switchers_mean, sub$percent_first_preference_switchers_std, n)
  avg_wait_std   <- total_variance(sub$avg_waiting_time_total_mean, sub$avg_waiting_time_total_std, n)
  avg_wait_sw_std <- total_variance(sub$avg_waiting_time_switchers_mean, sub$avg_waiting_time_switchers_std, n)

  tibble(
    pct_switch = pct_switch, pct_switch_std = pct_switch_std,
    pct_first = pct_first, pct_first_std = pct_first_std,
    avg_wait = avg_wait, avg_wait_std = avg_wait_std,
    avg_wait_sw = avg_wait_sw, avg_wait_sw_std = avg_wait_sw_std,
    total_nr_students = N
  )
}

# ---------------------------------------------------------------------------
# Table 1: Per municipality, rows = k values
#   Each metric block is 3 columns: DA / EADAM / TTC
# ---------------------------------------------------------------------------
for (muni in municipalities) {
  sub <- df %>% filter(municipality == muni)
  k_vals <- sort(unique(sub$k))

  da    <- sub %>% filter(algo == "DA")    %>% arrange(k)
  eadam <- sub %>% filter(algo == "EADAM") %>% arrange(k)
  ttc   <- sub %>% filter(algo == "TTC")   %>% arrange(k)

  lines <- c(
    "\\begin{table}[htbp]",
    "\\centering",
    "\\small",
    "\\begin{tabular}{l ccc | ccc | ccc | ccc}",
    "\\toprule",
    "\\textbf{Freq.}",
    "  & \\multicolumn{3}{c|}{\\textbf{\\% Switchers}}",
    "  & \\multicolumn{3}{c|}{\\textbf{\\% 1st Choice}}",
    "  & \\multicolumn{3}{c|}{\\textbf{Avg Waiting Time}}",
    "  & \\multicolumn{3}{c}{\\textbf{Avg Waiting Switchers}} \\\\",
    "\\cmidrule(lr){2-4}\\cmidrule(lr){5-7}\\cmidrule(lr){8-10}\\cmidrule(lr){11-13}",
    "  & \\underline{DA} & \\underline{EADAM} & \\underline{TTC}",
    "  & \\underline{DA} & \\underline{EADAM} & \\underline{TTC}",
    "  & \\underline{DA} & \\underline{EADAM} & \\underline{TTC}",
    "  & \\underline{DA} & \\underline{EADAM} & \\underline{TTC} \\\\",
    "\\midrule"
  )

  for (i in seq_along(k_vals)) {
    d <- da    %>% filter(k == k_vals[i])
    e <- eadam %>% filter(k == k_vals[i])
    t <- ttc   %>% filter(k == k_vals[i])

    val_line <- paste0(
      k_vals[i],
      "  & ", fmt_val(d$percent_switchers_mean, 2),                      "  & ", fmt_val(e$percent_switchers_mean, 2),                      "  & ", fmt_val(t$percent_switchers_mean, 2),
      "  & ", fmt_val(d$percent_first_preference_switchers_mean, 2),     "  & ", fmt_val(e$percent_first_preference_switchers_mean, 2),     "  & ", fmt_val(t$percent_first_preference_switchers_mean, 2),
      "  & ", fmt_val(d$avg_waiting_time_total_mean, 1),                 "  & ", fmt_val(e$avg_waiting_time_total_mean, 1),                 "  & ", fmt_val(t$avg_waiting_time_total_mean, 1),
      "  & ", fmt_val(d$avg_waiting_time_switchers_mean, 1),             "  & ", fmt_val(e$avg_waiting_time_switchers_mean, 1),             "  & ", fmt_val(t$avg_waiting_time_switchers_mean, 1),
      "  \\\\"
    )
    std_line <- paste0(
      "  & ", fmt_std(d$percent_switchers_std, 2),                  " & ", fmt_std(e$percent_switchers_std, 2),                  " & ", fmt_std(t$percent_switchers_std, 2),
      " & ", fmt_std(d$percent_first_preference_switchers_std, 2),  " & ", fmt_std(e$percent_first_preference_switchers_std, 2),  " & ", fmt_std(t$percent_first_preference_switchers_std, 2),
      " & ", fmt_std(d$avg_waiting_time_total_std, 1),              " & ", fmt_std(e$avg_waiting_time_total_std, 1),              " & ", fmt_std(t$avg_waiting_time_total_std, 1),
      " & ", fmt_std(d$avg_waiting_time_switchers_std, 1),          " & ", fmt_std(e$avg_waiting_time_switchers_std, 1),          " & ", fmt_std(t$avg_waiting_time_switchers_std, 1),
      if (i < length(k_vals)) " \\\\[4pt]" else " \\\\"
    )
    lines <- c(lines, val_line, std_line)
  }

  lines <- c(lines,
    "\\bottomrule",
    "\\end{tabular}",
    paste0("\\caption{Summary statistics for ", muni, " by placement round frequency (days). "),
    "Avg Waiting Time is measured in days, where students without a placement are assigned the maximum waiting time (end of program). ",
    "Avg Waiting Switchers is the average waiting time among students who received a school switch. ",
    "Standard deviations across 25 lottery draws in parentheses.}",
    paste0("\\label{tab:", gsub("ö", "o", gsub("ä", "a", tolower(muni))), "}"),
    "\\end{table}"
  )

  outpath <- file.path(out_dir, "mun_ks", paste0("output_", muni, ".tex"))
  dir.create(dirname(outpath), recursive = TRUE, showWarnings = FALSE)
  writeLines(lines, outpath)
  cat("Wrote", outpath, "\n")
}

# ---------------------------------------------------------------------------
# Table 2: Municipality summary, k = 90
#   Each metric block is 3 columns: DA / EADAM / TTC
# ---------------------------------------------------------------------------
{
  k_fix <- 90
  sub <- df %>% filter(k == k_fix)
  da    <- sub %>% filter(algo == "DA")    %>% arrange(municipality)
  eadam <- sub %>% filter(algo == "EADAM") %>% arrange(municipality)
  ttc   <- sub %>% filter(algo == "TTC")   %>% arrange(municipality)

  lines <- c(
    "\\begin{table}[htbp]",
    "\\centering",
    "\\small",
    "\\begin{tabular}{l l ccc | ccc}",
    "\\toprule",
    "\\textbf{Municipality (years)} & \\textbf{\\# ROLs}",
    "  & \\multicolumn{3}{c|}{\\textbf{\\% Switchers}}",
    "  & \\multicolumn{3}{c}{\\textbf{\\% 1st Choice}} \\\\",
    "\\cmidrule(lr){3-5}\\cmidrule(lr){6-8}",
    "  & & \\underline{DA} & \\underline{EADAM} & \\underline{TTC}",
    "  & \\underline{DA} & \\underline{EADAM} & \\underline{TTC} \\\\",
    "\\midrule"
  )

  for (i in seq_along(municipalities)) {
    m <- municipalities[i]
    d <- da    %>% filter(municipality == m)
    e <- eadam %>% filter(municipality == m)
    t <- ttc   %>% filter(municipality == m)

    val_line <- paste0(
      m, " (", muni_year_range[m], ") & ", round(d$total_nr_students_mean),
      "  & ", fmt_val(d$percent_switchers_mean, 2),                  "  & ", fmt_val(e$percent_switchers_mean, 2),                  "  & ", fmt_val(t$percent_switchers_mean, 2),
      "  & ", fmt_val(d$percent_first_preference_switchers_mean, 2), "  & ", fmt_val(e$percent_first_preference_switchers_mean, 2), "  & ", fmt_val(t$percent_first_preference_switchers_mean, 2),
      "  \\\\"
    )
    std_line <- paste0(
      " & ",
      "  & ", fmt_std(d$percent_switchers_std, 2),                  " & ", fmt_std(e$percent_switchers_std, 2),                  " & ", fmt_std(t$percent_switchers_std, 2),
      " & ", fmt_std(d$percent_first_preference_switchers_std, 2),  " & ", fmt_std(e$percent_first_preference_switchers_std, 2),  " & ", fmt_std(t$percent_first_preference_switchers_std, 2),
      if (i < length(municipalities)) " \\\\[4pt]" else " \\\\"
    )
    lines <- c(lines, val_line, std_line)
  }

  lines <- c(lines,
    "\\bottomrule",
    "\\end{tabular}",
    paste0("\\caption{Summary statistics by municipality (k = ", k_fix, " days). "),
    "Standard deviations across 25 lottery draws in parentheses.}",
    "\\label{tab:mun_summary}",
    "\\end{table}"
  )

  outpath <- file.path(out_dir, "mun_sum", "output_mun_summary.tex")
  dir.create(dirname(outpath), recursive = TRUE, showWarnings = FALSE)
  writeLines(lines, outpath)
  cat("Wrote", outpath, "\n")
}

# ---------------------------------------------------------------------------
# Table 1 (new format): per-muni at k=90 + italicised aggregated row
# Variant of the mun_sum table with comma-formatted ROL counts, no year range
# in the Municipality column, prose header labels, DA/EADAM/TTC without
# underline, and an italicised "Aggregated" row showing applicant-weighted
# means + law-of-total-variance stds. Written to analysis/output/table1.tex.
# Caption pulls n_iterations from plot_meta.json if available.
# ---------------------------------------------------------------------------
{
  k_fix <- 90
  sub   <- df %>% filter(k == k_fix)
  da    <- sub %>% filter(algo == "DA")    %>% arrange(municipality)
  eadam <- sub %>% filter(algo == "EADAM") %>% arrange(municipality)
  ttc   <- sub %>% filter(algo == "TTC")   %>% arrange(municipality)

  meta_path  <- file.path(project_root, "build", "output", "plot_meta.json")
  n_iter_str <- "?"
  if (requireNamespace("jsonlite", quietly = TRUE) && file.exists(meta_path)) {
    meta <- tryCatch(jsonlite::fromJSON(meta_path), error = function(e) list())
    if (!is.null(meta$n_iterations)) n_iter_str <- as.character(meta$n_iterations)
  }

  lines <- c(
    "\\begin{table}[htbp]",
    "\\centering",
    "\\small",
    "\\begin{tabular}{l l ccc | ccc}",
    "\\toprule",
    "\\textbf{Municipality} & \\textbf{No. ROLs}",
    "  & \\multicolumn{3}{c|}{\\textbf{Percent switchers}}",
    "  & \\multicolumn{3}{c}{\\textbf{Percent Assigned to First Choice}} \\\\",
    "\\cmidrule(lr){3-5}\\cmidrule(lr){6-8}",
    "  & & DA & EADAM & TTC",
    "  & DA & EADAM & TTC \\\\",
    "\\midrule"
  )

  for (i in seq_along(municipalities)) {
    mu <- municipalities[i]
    d <- da    %>% filter(municipality == mu)
    e <- eadam %>% filter(municipality == mu)
    t <- ttc   %>% filter(municipality == mu)

    nstud     <- round(d$total_nr_students_mean)
    nstud_fmt <- format(nstud, big.mark = ",")

    is_last <- (i == length(municipalities))
    sep <- if (is_last) " \\\\" else " \\\\[4pt]"

    val_line <- paste0(
      mu, " & ", nstud_fmt,
      "  & ", fmt_val(d$percent_switchers_mean, 2),                  "  & ", fmt_val(e$percent_switchers_mean, 2),                  "  & ", fmt_val(t$percent_switchers_mean, 2),
      "  & ", fmt_val(d$percent_first_preference_switchers_mean, 2), "  & ", fmt_val(e$percent_first_preference_switchers_mean, 2), "  & ", fmt_val(t$percent_first_preference_switchers_mean, 2),
      "  \\\\"
    )
    std_line <- paste0(
      " & ",
      "  & ", fmt_std(d$percent_switchers_std, 2),                 " & ", fmt_std(e$percent_switchers_std, 2),                 " & ", fmt_std(t$percent_switchers_std, 2),
      " & ", fmt_std(d$percent_first_preference_switchers_std, 2), " & ", fmt_std(e$percent_first_preference_switchers_std, 2), " & ", fmt_std(t$percent_first_preference_switchers_std, 2),
      sep
    )
    lines <- c(lines, val_line, std_line)
  }

  # Aggregated row (italicised, applicant-weighted + law-of-total-variance).
  agg_da    <- aggregate_stats(df, "DA",    k_fix)
  agg_eadam <- aggregate_stats(df, "EADAM", k_fix)
  agg_ttc   <- aggregate_stats(df, "TTC",   k_fix)
  nstud_agg     <- round(agg_da$total_nr_students)
  nstud_agg_fmt <- format(nstud_agg, big.mark = ",")
  lines <- c(lines, "\\midrule",
    paste0(
      "\\emph{Aggregated}$^{\\dagger}$ & \\emph{", nstud_agg_fmt, "}",
      " & \\emph{", fmt_val(agg_da$pct_switch, 2), "} & \\emph{", fmt_val(agg_eadam$pct_switch, 2), "} & \\emph{", fmt_val(agg_ttc$pct_switch, 2), "}",
      " & \\emph{", fmt_val(agg_da$pct_first,  2), "} & \\emph{", fmt_val(agg_eadam$pct_first,  2), "} & \\emph{", fmt_val(agg_ttc$pct_first,  2), "}",
      "  \\\\"
    ),
    paste0(
      " & ",
      " & \\emph{(", fmt_val(agg_da$pct_switch_std, 2), ")} & \\emph{(", fmt_val(agg_eadam$pct_switch_std, 2), ")} & \\emph{(", fmt_val(agg_ttc$pct_switch_std, 2), ")}",
      " & \\emph{(", fmt_val(agg_da$pct_first_std,  2), ")} & \\emph{(", fmt_val(agg_eadam$pct_first_std,  2), ")} & \\emph{(", fmt_val(agg_ttc$pct_first_std,  2), ")}",
      " \\\\"
    )
  )

  lines <- c(lines,
    "\\bottomrule",
    "\\end{tabular}",
    paste0("\\caption{Summary statistics by municipality ($k=", k_fix, "$). "),
    paste0("Standard deviations across ", n_iter_str, " lottery draws in parentheses. ",
           "$^\\dagger$Includes cross-district variation via the law of total variance.}"),
    "\\label{tab:table1}",
    "\\end{table}"
  )
  outpath <- file.path(out_dir, "table1.tex")
  writeLines(lines, outpath)
  cat("Wrote", outpath, "\n")
}

# ---------------------------------------------------------------------------
# Table 3: Aggregated across municipalities, rows = k values
#   Each metric block is 3 columns: DA / EADAM / TTC
# ---------------------------------------------------------------------------
{
  k_vals <- sort(unique(df$k))

  lines <- c(
    "\\begin{table}[htbp]",
    "\\centering",
    "\\small",
    "\\begin{tabular}{l ccc | ccc | ccc | ccc}",
    "\\toprule",
    "\\textbf{Freq.}",
    "  & \\multicolumn{3}{c|}{\\textbf{\\% Switchers}}",
    "  & \\multicolumn{3}{c|}{\\textbf{\\% 1st Choice}}",
    "  & \\multicolumn{3}{c|}{\\textbf{Avg Waiting Time}}",
    "  & \\multicolumn{3}{c}{\\textbf{Avg Waiting Time (Switchers)}} \\\\",
    "\\cmidrule(lr){2-4}\\cmidrule(lr){5-7}\\cmidrule(lr){8-10}\\cmidrule(lr){11-13}",
    "  & \\underline{DA} & \\underline{EADAM} & \\underline{TTC}",
    "  & \\underline{DA} & \\underline{EADAM} & \\underline{TTC}",
    "  & \\underline{DA} & \\underline{EADAM} & \\underline{TTC}",
    "  & \\underline{DA} & \\underline{EADAM} & \\underline{TTC} \\\\",
    "\\midrule"
  )

  for (i in seq_along(k_vals)) {
    kv <- k_vals[i]
    da_agg    <- aggregate_stats(df, "DA",    kv)
    eadam_agg <- aggregate_stats(df, "EADAM", kv)
    ttc_agg   <- aggregate_stats(df, "TTC",   kv)

    val_line <- paste0(
      kv,
      "  & ", fmt_val(da_agg$pct_switch, 2),  "  & ", fmt_val(eadam_agg$pct_switch, 2),  "  & ", fmt_val(ttc_agg$pct_switch, 2),
      "  & ", fmt_val(da_agg$pct_first, 2),   "  & ", fmt_val(eadam_agg$pct_first, 2),   "  & ", fmt_val(ttc_agg$pct_first, 2),
      "  & ", fmt_val(da_agg$avg_wait, 1),    "  & ", fmt_val(eadam_agg$avg_wait, 1),    "  & ", fmt_val(ttc_agg$avg_wait, 1),
      "  & ", fmt_val(da_agg$avg_wait_sw, 1), "  & ", fmt_val(eadam_agg$avg_wait_sw, 1), "  & ", fmt_val(ttc_agg$avg_wait_sw, 1),
      "  \\\\"
    )
    std_line <- paste0(
      "  & ", fmt_std(da_agg$pct_switch_std, 2),  " & ", fmt_std(eadam_agg$pct_switch_std, 2),  " & ", fmt_std(ttc_agg$pct_switch_std, 2),
      " & ", fmt_std(da_agg$pct_first_std, 2),    " & ", fmt_std(eadam_agg$pct_first_std, 2),    " & ", fmt_std(ttc_agg$pct_first_std, 2),
      " & ", fmt_std(da_agg$avg_wait_std, 1),     " & ", fmt_std(eadam_agg$avg_wait_std, 1),     " & ", fmt_std(ttc_agg$avg_wait_std, 1),
      " & ", fmt_std(da_agg$avg_wait_sw_std, 1),  " & ", fmt_std(eadam_agg$avg_wait_sw_std, 1),  " & ", fmt_std(ttc_agg$avg_wait_sw_std, 1),
      if (i < length(k_vals)) " \\\\[4pt]" else " \\\\"
    )
    lines <- c(lines, val_line, std_line)
  }

  lines <- c(lines,
    "\\bottomrule",
    "\\end{tabular}",
    "\\caption{Aggregated summary statistics across municipalities by placement round frequency (days). ",
    "Avg Waiting Time is measured in days, where students without a placement are assigned the maximum waiting time. ",
    "Avg Waiting Time (Switchers) is the average waiting time among students who received a school switch. ",
    "Applicant-weighted standard deviations across 25 lottery draws and municipalities in parentheses.}",
    "\\label{tab:sum_k}",
    "\\end{table}"
  )

  outpath <- file.path(out_dir, "sum_k", "output_sum_k.tex")
  dir.create(dirname(outpath), recursive = TRUE, showWarnings = FALSE)
  writeLines(lines, outpath)
  cat("Wrote", outpath, "\n")
}

# ---------------------------------------------------------------------------
# Table 4: Aggregated, k = 90 — single row, columns = 3 algos × 2 metrics
# (mirrors the per-muni table 2 layout, with no row label)
# ---------------------------------------------------------------------------
{
  k_fix <- 90

  da_agg    <- aggregate_stats(df, "DA",    k_fix)
  eadam_agg <- aggregate_stats(df, "EADAM", k_fix)
  ttc_agg   <- aggregate_stats(df, "TTC",   k_fix)

  lines <- c(
    "\\begin{table}[htbp]",
    "\\centering",
    "\\small",
    "\\begin{tabular}{l ccc | ccc}",
    "\\toprule",
    " & \\multicolumn{3}{c|}{\\textbf{\\% Switchers}}",
    " & \\multicolumn{3}{c}{\\textbf{\\% 1st Choice}} \\\\",
    "\\cmidrule(lr){2-4}\\cmidrule(lr){5-7}",
    " & \\underline{DA} & \\underline{EADAM} & \\underline{TTC}",
    " & \\underline{DA} & \\underline{EADAM} & \\underline{TTC} \\\\",
    "\\midrule",
    paste0(
      "  & ", fmt_val(da_agg$pct_switch, 2),  "  & ", fmt_val(eadam_agg$pct_switch, 2),  "  & ", fmt_val(ttc_agg$pct_switch, 2),
      "  & ", fmt_val(da_agg$pct_first,  2),  "  & ", fmt_val(eadam_agg$pct_first,  2),  "  & ", fmt_val(ttc_agg$pct_first,  2),
      "  \\\\"
    ),
    paste0(
      " & ", fmt_std(da_agg$pct_switch_std, 2),  " & ", fmt_std(eadam_agg$pct_switch_std, 2),  " & ", fmt_std(ttc_agg$pct_switch_std, 2),
      " & ", fmt_std(da_agg$pct_first_std,  2),  " & ", fmt_std(eadam_agg$pct_first_std,  2),  " & ", fmt_std(ttc_agg$pct_first_std,  2),
      " \\\\"
    ),
    "\\bottomrule",
    "\\end{tabular}",
    paste0("\\caption{Aggregated summary statistics (k = ", k_fix, " days). "),
    "Applicant-weighted standard deviations across 25 lottery draws and municipalities in parentheses.}",
    "\\label{tab:sum}",
    "\\end{table}"
  )

  outpath <- file.path(out_dir, "sum", "output_sum.tex")
  dir.create(dirname(outpath), recursive = TRUE, showWarnings = FALSE)
  writeLines(lines, outpath)
  cat("Wrote", outpath, "\n")
}
