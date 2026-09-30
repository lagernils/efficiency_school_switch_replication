# =============================================================================
# make_tables.R
#
# Reads per-municipality CSVs from build/output/loop_results/ and writes four
# LaTeX tables to analysis/output/ with DA / EADAM / TTC columns side by side:
#   1. table_mun_ks_{municipality}.tex   (per municipality x k)
#   2. table_mun_sum.tex                  (per municipality, at k=90)
#   3. table_sum_k.tex                    (aggregated across municipalities x k)
#   4. table_sum.tex                      (aggregated, at k=90)
#
# The aggregated tables (3 and 4) are computed inline via applicant-weighted
# means and the law of total variance, so this script does not depend on the
# Python `summary_stats_{algo}_ALL.csv` files (which only exist for DA and TTC).
#
# Skips silently if the per-muni CSVs are absent (e.g., when masterfile is in
# basecapacity-loop mode and only writes lite-mode CSVs to a different folder).
# =============================================================================

suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tidyr)
  library(glue)
})

# ---- Locate project root ----------------------------------------------------
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

build_out <- file.path(project_root, "build", "output", "loop_results")
out_dir   <- file.path(project_root, "analysis", "output")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

# ---- Helpers ----------------------------------------------------------------
municipalities <- c("Linköping", "Malmö", "Nacka", "Norrköping", "Uppsala", "Växjö")
algos          <- c("DA", "EADAM", "TTC")     # display order
focal_k        <- 90

# Early-exit if no per-muni CSVs are present (e.g., basecapacity-loop mode
# wrote lite-mode files to a different folder).
if (!dir.exists(build_out)) {
  message("[make_tables] ", build_out, " not found -- skipping table generation.")
  quit(status = 0)
}
sample_path <- file.path(build_out, glue("summary_stats_DA_{municipalities[1]}.csv"))
if (!file.exists(sample_path)) {
  message("[make_tables] no summary_stats_*.csv in ", build_out,
          " -- skipping table generation.")
  quit(status = 0)
}

# Academic-year ranges shown in the Municipality column of Table 2.
# Mirrors the per-municipality lists in
# build/code/functions/config.py:ACADEMIC_YEARS — keep in sync.
muni_year_range <- c(
  "Linköping"  = "2020--2025",
  "Malmö"      = "2020--2025",
  "Nacka"      = "2021--2025",
  "Norrköping" = "2022--2025",
  "Uppsala"    = "2021--2026",
  "Växjö"      = "2023--2025"
)

# Single-value mean / std formatters used by the nested-booktabs Tables 2 & 4.
fmt_v <- function(x, digits = 2) sprintf(paste0("%.", digits, "f"), x)
fmt_s <- function(x, digits = 2) sprintf("(%.*f)", digits, x)

read_one <- function(algo, suffix) {
  path <- file.path(build_out, glue("summary_stats_{algo}_{suffix}.csv"))
  if (!file.exists(path)) return(NULL)
  df <- suppressMessages(read_csv(path, show_col_types = FALSE))
  df$algo <- algo
  df$source <- suffix
  df
}

fmt_mean_sd <- function(mean, sd, digits = 2) {
  ifelse(is.na(mean),
         "--",
         sprintf(paste0("%.", digits, "f (%.", digits, "f)"), mean, sd))
}

# Default column / label set used by per-municipality tables.
ALL_STATS <- list(
  cols   = c("pct_switchers", "pct_first_pref_switchers",
             "avg_wait_all",  "avg_wait_switchers"),
  labels = c("\\% switchers", "\\% 1st-pref switchers",
             "avg wait (all)", "avg wait (switch)")
)

# Build a wide row with one mean(sd) cell per (algo, statistic).
# `algo_dfs` is a named list, e.g. list(DA = df_da, EADAM = df_eadam, TTC = df_ttc).
build_wide_row <- function(algo_dfs, stat_cols) {
  out <- list()
  for (col in stat_cols) {
    for (algo in algos) {
      d <- algo_dfs[[algo]]
      out[[paste0(algo, "_", col)]] <- fmt_mean_sd(
        d[[paste0(col, "_mean")]],
        d[[paste0(col, "_std")]]
      )
    }
  }
  as.data.frame(out, stringsAsFactors = FALSE)
}

write_latex_table <- function(df, path, caption, row_header, std_note, stat_labels) {
  n_cols <- ncol(df)
  align <- paste0("l", paste(rep("r", n_cols - 1), collapse = ""))
  header1 <- paste0(c(row_header,
                      rep(algos, length(stat_labels))),
                    collapse = " & ")
  header2_cells <- c("")
  for (lbl in stat_labels) header2_cells <- c(header2_cells, rep(lbl, length(algos)))
  header2 <- paste0(header2_cells, collapse = " & ")
  body <- apply(df, 1, function(row) paste(row, collapse = " & "))
  body <- paste0(body, " \\\\")
  tex <- c(
    "\\begin{table}[h]",
    "\\centering",
    paste0("\\caption{", caption, " ", std_note, "}"),
    paste0("\\begin{tabular}{", align, "}"),
    "\\hline",
    paste0(header1, " \\\\"),
    paste0(header2, " \\\\"),
    "\\hline",
    body,
    "\\hline",
    "\\end{tabular}",
    "\\end{table}"
  )
  writeLines(tex, path)
  message("  wrote ", path)
}

# Read all three algo CSVs for a given suffix (municipality name or "ALL").
# Returns NULL if any of the three files is missing.
read_all_algos <- function(suffix) {
  out <- lapply(algos, function(a) read_one(a, suffix))
  names(out) <- algos
  if (any(sapply(out, is.null))) return(NULL)
  out
}

# Pick the rows for a given k from each algo's data frame.
slice_at_k <- function(algo_dfs, k_val) {
  rows <- lapply(algo_dfs, function(d) d[d$k == k_val, , drop = FALSE])
  names(rows) <- names(algo_dfs)
  if (any(sapply(rows, nrow) == 0)) return(NULL)
  rows
}

# Applicant-weighted aggregate across municipalities for one (algo, k) pair.
# Returns a one-row data frame with the same column conventions as a per-muni
# read_one() row, so it slots into build_wide_row() unchanged.
aggregate_across_munis <- function(algo, k_val) {
  per_muni <- lapply(municipalities, function(m) read_one(algo, m))
  per_muni <- per_muni[!sapply(per_muni, is.null)]
  per_muni <- lapply(per_muni, function(d) d[d$k == k_val, , drop = FALSE])
  per_muni <- per_muni[sapply(per_muni, nrow) > 0]
  if (length(per_muni) == 0) return(NULL)

  weights <- sapply(per_muni, function(d) d$total_students_mean[1])
  N <- sum(weights)
  if (N == 0) return(NULL)

  out <- list(k = k_val, total_students_mean = N, total_students_std = 0)
  for (col in ALL_STATS$cols) {
    means <- sapply(per_muni, function(d) d[[paste0(col, "_mean")]][1])
    stds  <- sapply(per_muni, function(d) d[[paste0(col, "_std")]][1])
    grand_mean <- sum(weights * means) / N
    within_var  <- sum(weights * stds^2) / N
    between_var <- sum(weights * (means - grand_mean)^2) / N
    out[[paste0(col, "_mean")]] <- grand_mean
    out[[paste0(col, "_std")]]  <- sqrt(within_var + between_var)
  }
  as.data.frame(out, stringsAsFactors = FALSE)
}

# ---- Per-table column / label subsets ---------------------------------------
PCT_ONLY <- list(cols   = c("pct_switchers", "pct_first_pref_switchers"),
                 labels = c("\\% switchers", "\\% 1st-pref switchers"))

# ---- Table 1: per municipality × k ------------------------------------------
message("[make_tables] table 1: per municipality x k")
for (mun in municipalities) {
  algo_dfs <- read_all_algos(mun)
  if (is.null(algo_dfs)) next

  ks <- sort(unique(unlist(lapply(algo_dfs, function(d) d$k))))
  rows <- lapply(ks, function(k) {
    sliced <- slice_at_k(algo_dfs, k)
    if (is.null(sliced)) return(NULL)
    cbind(k = k, build_wide_row(sliced, ALL_STATS$cols))
  })
  rows <- do.call(rbind, rows)
  if (is.null(rows) || nrow(rows) == 0) next

  path <- file.path(out_dir, glue("table_mun_ks_{mun}.tex"))
  write_latex_table(rows, path,
                    caption = glue("{mun}: outcomes by k."),
                    row_header = "k",
                    std_note = "Standard deviations across 25 lottery draws in parentheses.",
                    stat_labels = ALL_STATS$labels)
}

# ---- Table 2: per municipality at k = 90, nested booktabs layout -----------
# Layout: Muni (years) | # ROLs | DA EADAM TTC (% switchers) | DA EADAM TTC (% 1st choice).
message("[make_tables] table 2: per municipality at k=", focal_k)
{
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

  any_row <- FALSE
  for (i in seq_along(municipalities)) {
    m <- municipalities[i]
    algo_dfs <- read_all_algos(m)
    if (is.null(algo_dfs)) next
    sliced <- slice_at_k(algo_dfs, focal_k)
    if (is.null(sliced)) next
    any_row <- TRUE

    nstud <- round(sliced$DA$total_students_mean[1])

    pct_switch  <- function(d) d$pct_switchers_mean[1]
    pct_first   <- function(d) d$pct_first_pref_switchers_mean[1]
    pct_switch_sd <- function(d) d$pct_switchers_std[1]
    pct_first_sd  <- function(d) d$pct_first_pref_switchers_std[1]

    val_line <- paste0(
      m, " (", muni_year_range[m], ") & ", nstud,
      "  & ", fmt_v(pct_switch(sliced$DA), 2),  "  & ", fmt_v(pct_switch(sliced$EADAM), 2),  "  & ", fmt_v(pct_switch(sliced$TTC), 2),
      "  & ", fmt_v(pct_first(sliced$DA),  2),  "  & ", fmt_v(pct_first(sliced$EADAM),  2),  "  & ", fmt_v(pct_first(sliced$TTC),  2),
      "  \\\\"
    )
    sep <- if (i < length(municipalities)) " \\\\[4pt]" else " \\\\"
    std_line <- paste0(
      " & ",
      "  & ", fmt_s(pct_switch_sd(sliced$DA), 2),  " & ", fmt_s(pct_switch_sd(sliced$EADAM), 2),  " & ", fmt_s(pct_switch_sd(sliced$TTC), 2),
      " & ", fmt_s(pct_first_sd(sliced$DA),  2),  " & ", fmt_s(pct_first_sd(sliced$EADAM),  2),  " & ", fmt_s(pct_first_sd(sliced$TTC),  2),
      sep
    )
    lines <- c(lines, val_line, std_line)
  }

  if (any_row) {
    lines <- c(lines,
      "\\bottomrule",
      "\\end{tabular}",
      paste0("\\caption{Summary statistics by municipality (k = ", focal_k, " days). "),
      "Standard deviations across 25 lottery draws in parentheses.}",
      "\\label{tab:mun_summary}",
      "\\end{table}"
    )
    outpath <- file.path(out_dir, "table_mun_sum.tex")
    writeLines(lines, outpath)
    message("  wrote ", outpath)
  }
}

# ---- Table 1 (new format): per-muni at k=90 + italicised aggregated row ----
# Same data as table_mun_sum but with: comma-formatted ROL counts, no year
# range in the Municipality column, prose header labels ("Percent switchers"
# / "Percent 1st Choices"), DA/EADAM/TTC without underline, and an italicised
# "Aggregated" row showing applicant-weighted means + law-of-total-variance
# stds. Written to analysis/output/table1.tex (top of analysis/output, not a
# subfolder). Caption pulls n_iterations from plot_meta.json if available.
message("[make_tables] table1: per municipality at k=", focal_k, " + aggregated row")
{
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

  any_row <- FALSE
  for (i in seq_along(municipalities)) {
    mu <- municipalities[i]
    algo_dfs <- read_all_algos(mu)
    if (is.null(algo_dfs)) next
    sliced <- slice_at_k(algo_dfs, focal_k)
    if (is.null(sliced)) next
    any_row <- TRUE

    nstud     <- round(sliced$DA$total_students_mean[1])
    nstud_fmt <- format(nstud, big.mark = ",")

    pct_switch    <- function(d) d$pct_switchers_mean[1]
    pct_first     <- function(d) d$pct_first_pref_switchers_mean[1]
    pct_switch_sd <- function(d) d$pct_switchers_std[1]
    pct_first_sd  <- function(d) d$pct_first_pref_switchers_std[1]

    is_last <- (i == length(municipalities))
    sep <- if (is_last) " \\\\" else " \\\\[4pt]"

    val_line <- paste0(
      mu, " & ", nstud_fmt,
      "  & ", fmt_v(pct_switch(sliced$DA), 2),  "  & ", fmt_v(pct_switch(sliced$EADAM), 2),  "  & ", fmt_v(pct_switch(sliced$TTC), 2),
      "  & ", fmt_v(pct_first(sliced$DA),  2),  "  & ", fmt_v(pct_first(sliced$EADAM),  2),  "  & ", fmt_v(pct_first(sliced$TTC),  2),
      "  \\\\"
    )
    std_line <- paste0(
      " & ",
      "  & ", fmt_s(pct_switch_sd(sliced$DA), 2),  " & ", fmt_s(pct_switch_sd(sliced$EADAM), 2),  " & ", fmt_s(pct_switch_sd(sliced$TTC), 2),
      " & ", fmt_s(pct_first_sd(sliced$DA),  2),  " & ", fmt_s(pct_first_sd(sliced$EADAM),  2),  " & ", fmt_s(pct_first_sd(sliced$TTC),  2),
      sep
    )
    lines <- c(lines, val_line, std_line)
  }

  if (any_row) {
    agg_da    <- aggregate_across_munis("DA",    focal_k)
    agg_eadam <- aggregate_across_munis("EADAM", focal_k)
    agg_ttc   <- aggregate_across_munis("TTC",   focal_k)
    if (!any(sapply(list(agg_da, agg_eadam, agg_ttc), is.null))) {
      nstud_agg     <- round(agg_da$total_students_mean[1])
      nstud_agg_fmt <- format(nstud_agg, big.mark = ",")
      lines <- c(lines, "\\midrule",
        paste0(
          # RR1 (standard deviations): the dagger marks the aggregated row, whose
          # standard deviation is not an average of the per-district Monte Carlo
          # standard deviations but combines them with the cross-district variance
          # via the law of total variance. The note is added to the caption below.
          "\\emph{Aggregated}$^{\\dagger}$ & \\emph{", nstud_agg_fmt, "}",
          " & \\emph{", fmt_v(agg_da$pct_switchers_mean,            2), "} & \\emph{", fmt_v(agg_eadam$pct_switchers_mean,            2), "} & \\emph{", fmt_v(agg_ttc$pct_switchers_mean,            2), "}",
          " & \\emph{", fmt_v(agg_da$pct_first_pref_switchers_mean, 2), "} & \\emph{", fmt_v(agg_eadam$pct_first_pref_switchers_mean, 2), "} & \\emph{", fmt_v(agg_ttc$pct_first_pref_switchers_mean, 2), "}",
          "  \\\\"
        ),
        paste0(
          " & ",
          " & \\emph{(", fmt_v(agg_da$pct_switchers_std,            2), ")} & \\emph{(", fmt_v(agg_eadam$pct_switchers_std,            2), ")} & \\emph{(", fmt_v(agg_ttc$pct_switchers_std,            2), ")}",
          " & \\emph{(", fmt_v(agg_da$pct_first_pref_switchers_std, 2), ")} & \\emph{(", fmt_v(agg_eadam$pct_first_pref_switchers_std, 2), ")} & \\emph{(", fmt_v(agg_ttc$pct_first_pref_switchers_std, 2), ")}",
          " \\\\"
        )
      )
    }

    lines <- c(lines,
      "\\bottomrule",
      "\\end{tabular}",
      paste0("\\caption{Summary statistics by municipality ($k=", focal_k, "$). "),
      paste0("Standard deviations across ", n_iter_str, " lottery draws in parentheses. "),
      "$^\\dagger$Includes cross-district variation via the law of total variance.}",
      "\\label{tab:table1}",
      "\\end{table}"
    )
    outpath <- file.path(out_dir, "table1.tex")
    writeLines(lines, outpath)
    message("  wrote ", outpath)
  }
}

# ---- Table 3: aggregated across municipalities × k --------------------------
# Aggregate inline (do not rely on Python's *_ALL.csv, which doesn't exist for
# EADAM). Pick the union of k values present in any algo's per-muni data.
message("[make_tables] table 3: aggregated x k")
sample_dfs <- read_all_algos(municipalities[1])
if (!is.null(sample_dfs)) {
  ks <- sort(unique(unlist(lapply(sample_dfs, function(d) d$k))))
  rows <- lapply(ks, function(k) {
    aggs <- setNames(lapply(algos, function(a) aggregate_across_munis(a, k)), algos)
    if (any(sapply(aggs, is.null))) return(NULL)
    cbind(k = k, build_wide_row(aggs, ALL_STATS$cols))
  })
  rows <- do.call(rbind, rows)
  if (!is.null(rows) && nrow(rows) > 0) {
    write_latex_table(rows, file.path(out_dir, "table_sum_k.tex"),
                      caption = "Cross-municipality outcomes by k (applicant-weighted).",
                      row_header = "k",
                      std_note = "Applicant-weighted standard deviations across 25 lottery draws and municipalities in parentheses.",
                      stat_labels = ALL_STATS$labels)
  }

  # ---- Table 4: aggregated at k = 90, nested booktabs (no row label) -------
  # Single row of values + std, columns = 3 algos under each of 2 metric blocks.
  message("[make_tables] table 4: aggregated at k=", focal_k)
  aggs <- setNames(lapply(algos, function(a) aggregate_across_munis(a, focal_k)), algos)
  if (!any(sapply(aggs, is.null))) {
    pct_switch    <- function(d) d$pct_switchers_mean[1]
    pct_first     <- function(d) d$pct_first_pref_switchers_mean[1]
    pct_switch_sd <- function(d) d$pct_switchers_std[1]
    pct_first_sd  <- function(d) d$pct_first_pref_switchers_std[1]

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
        "  & ", fmt_v(pct_switch(aggs$DA), 2),  "  & ", fmt_v(pct_switch(aggs$EADAM), 2),  "  & ", fmt_v(pct_switch(aggs$TTC), 2),
        "  & ", fmt_v(pct_first(aggs$DA),  2),  "  & ", fmt_v(pct_first(aggs$EADAM),  2),  "  & ", fmt_v(pct_first(aggs$TTC),  2),
        "  \\\\"
      ),
      paste0(
        " & ", fmt_s(pct_switch_sd(aggs$DA), 2),  " & ", fmt_s(pct_switch_sd(aggs$EADAM), 2),  " & ", fmt_s(pct_switch_sd(aggs$TTC), 2),
        " & ", fmt_s(pct_first_sd(aggs$DA),  2),  " & ", fmt_s(pct_first_sd(aggs$EADAM),  2),  " & ", fmt_s(pct_first_sd(aggs$TTC),  2),
        " \\\\"
      ),
      "\\bottomrule",
      "\\end{tabular}",
      paste0("\\caption{Aggregated summary statistics (k = ", focal_k, " days). "),
      "Applicant-weighted standard deviations across 25 lottery draws and municipalities in parentheses.}",
      "\\label{tab:sum}",
      "\\end{table}"
    )
    outpath <- file.path(out_dir, "table_sum.tex")
    writeLines(lines, outpath)
    message("  wrote ", outpath)
  }
}

message("[make_tables] done")
