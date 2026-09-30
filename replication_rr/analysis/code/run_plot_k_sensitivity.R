# =============================================================================
# run_plot_k_sensitivity.R
#
# Two-panel figure showing how outcomes vary with the placement-round
# spacing k (days between matching runs):
#   Left:  Share of students reassigned (%) under DA, EADAM, TTC.
#   Right: Average waiting time (days, all applicants) under DA, EADAM, TTC.
# In both panels, a shaded ribbon marks the "efficiency gap" between DA
# (lower bound on share reassigned, upper bound on waiting time) and the
# mean of the two efficient mechanisms.
#
# Inputs (all in <project>/build/output/loop_results/):
#   summary_stats_<DA|EADAM|TTC>_<muni>.csv -- per-muni summary outputs
# Optional metadata:
#   <project>/build/output/plot_meta.json   -- run-context (n_iterations etc.)
#                                              for the caption.
#
# Outputs (in <project>/analysis/output/sum_k/):
#   plot_k_sensitivity.png   -- always written via ragg or default device
#   plot_k_sensitivity.pdf   -- optional, via cairo_pdf if available
#   plot_k_sensitivity.tex   -- LaTeX figure wrapper that \input's the PNG
# =============================================================================

suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tidyr)
  library(ggplot2)
})
have_jsonlite  <- requireNamespace("jsonlite", quietly = TRUE)
have_patchwork <- requireNamespace("patchwork", quietly = TRUE)
if (!have_patchwork) {
  stop("[plot_k_sensitivity] The 'patchwork' package is required for the ",
       "side-by-side panels. Install with: install.packages('patchwork').")
}
suppressPackageStartupMessages(library(patchwork))

`%||%` <- function(a, b) if (is.null(a) || (length(a) == 1 && is.na(a))) b else a

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
out_dir   <- file.path(project_root, "analysis", "output", "sum_k")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

if (!dir.exists(build_out)) {
  message("[plot_k_sensitivity] ", build_out, " not found -- nothing to plot.")
  quit(status = 0)
}

# ---- Read per-municipality CSVs --------------------------------------------
files <- list.files(build_out,
                    pattern = "^summary_stats_(DA|EADAM|TTC)_.+\\.csv$",
                    full.names = TRUE)
if (length(files) == 0) {
  message("[plot_k_sensitivity] no summary_stats_*.csv files in ", build_out)
  quit(status = 0)
}

parse_one <- function(f) {
  m <- regmatches(basename(f),
                  regexec("^summary_stats_(DA|EADAM|TTC)_(.+)\\.csv$", basename(f)))[[1]]
  if (length(m) < 3) return(NULL)
  df <- suppressMessages(read_csv(f, show_col_types = FALSE))
  df$algo <- m[2]
  df$muni <- m[3]
  df
}
all_df <- do.call(rbind, lapply(files, parse_one))
all_df <- all_df[!is.na(all_df$muni) & all_df$muni != "ALL", ]
if (nrow(all_df) == 0) {
  message("[plot_k_sensitivity] no per-muni rows after filtering -- nothing to plot.")
  quit(status = 0)
}

# ---- Optional metadata for caption ------------------------------------------
meta <- list()
meta_path <- file.path(project_root, "build", "output", "plot_meta.json")
if (have_jsonlite && file.exists(meta_path)) {
  meta <- tryCatch(jsonlite::fromJSON(meta_path), error = function(e) list())
}
n_iterations <- as.integer(meta$n_iterations %||% NA)
munis_meta   <- meta$list_of_municipalities %||% NULL
random_priors <- isTRUE(meta$random_priorities %||% NA)
full_consent  <- isTRUE(meta$full_consent_bool %||% NA)

# ---- Applicant-weighted aggregation across municipalities -------------------
agg <- all_df |>
  dplyr::group_by(algo, k) |>
  dplyr::summarise(
    n_total        = sum(total_students_mean),
    pct_switchers  = sum(pct_switchers_mean * total_students_mean) / sum(total_students_mean),
    pct_first_pref = sum(pct_first_pref_switchers_mean * total_students_mean) / sum(total_students_mean),
    .groups = "drop"
  ) |>
  dplyr::arrange(algo, k)

ks <- sort(unique(agg$k))

# Pivot wide for the ribbon (one row per k with DA/EADAM/TTC columns).
wide <- agg |>
  dplyr::select(algo, k, pct_switchers, pct_first_pref) |>
  tidyr::pivot_wider(names_from = algo,
                     values_from = c(pct_switchers, pct_first_pref)) |>
  dplyr::arrange(k)
have_all_three <- all(c("pct_switchers_DA", "pct_switchers_EADAM",
                         "pct_switchers_TTC", "pct_first_pref_DA",
                         "pct_first_pref_EADAM", "pct_first_pref_TTC") %in% names(wide))
if (have_all_three) {
  wide$eff_mean_switch <- (wide$pct_switchers_EADAM  + wide$pct_switchers_TTC)  / 2
  wide$eff_mean_first  <- (wide$pct_first_pref_EADAM + wide$pct_first_pref_TTC) / 2
  ribbon_data <- wide
} else {
  message("[plot_k_sensitivity] need DA, EADAM and TTC rows; got ",
          paste(names(wide), collapse = ", "), " -- skipping ribbon.")
  ribbon_data <- wide[FALSE, ]
}

# ---- Font and device setup --------------------------------------------------
# Use Times New Roman to match the paper's LaTeX font (\rmdefault = ptm).
# Same logic as run_plot_basecapacity.R.
plot_font <- "Times New Roman"
use_custom_font <- FALSE
use_ragg <- requireNamespace("ragg", quietly = TRUE) &&
            requireNamespace("systemfonts", quietly = TRUE)

if (use_ragg) {
  fams <- tryCatch(systemfonts::system_fonts()$family,
                   error = function(e) character(0))
  if (any(grepl("^Times New Roman$", fams))) {
    use_custom_font <- TRUE
  } else if (any(grepl("^Times$", fams))) {
    plot_font <- "Times"
    use_custom_font <- TRUE
  }
}

if (!use_custom_font &&
    requireNamespace("showtext", quietly = TRUE) &&
    requireNamespace("sysfonts", quietly = TRUE)) {
  ff <- tryCatch(sysfonts::font_files(), error = function(e) NULL)
  if (!is.null(ff) && nrow(ff) > 0) {
    rx <- function(p) grepl(p, ff$file, ignore.case = TRUE)
    reg_i <- which(rx("^Times[ -]?New[ -]?Roman\\.") |
                   rx("^Times-Roman\\.") |
                   rx("^Times\\.(ttf|ttc|otf)$"))
    if (length(reg_i) > 0) {
      bold_i <- which(rx("^Times[ -]?New[ -]?Roman[ -]?Bold\\.") |
                       rx("^Times-Bold\\."))
      ital_i <- which(rx("^Times[ -]?New[ -]?Roman[ -]?Italic\\.") |
                       rx("^Times-Italic\\."))
      reg_p  <- file.path(ff$path[reg_i[1]],  ff$file[reg_i[1]])
      bold_p <- if (length(bold_i)) file.path(ff$path[bold_i[1]], ff$file[bold_i[1]]) else reg_p
      ital_p <- if (length(ital_i)) file.path(ff$path[ital_i[1]], ff$file[ital_i[1]]) else reg_p
      tryCatch({
        sysfonts::font_add(family = plot_font, regular = reg_p,
                           bold = bold_p, italic = ital_p)
        showtext::showtext_auto()
        showtext::showtext_opts(dpi = 200)
        use_custom_font <- TRUE
      }, error = function(e) {})
    }
  }
}

if (!use_custom_font) {
  message("[plot_k_sensitivity] Times New Roman unavailable; using default font.")
  plot_font <- ""
}

# ---- Plot styling -----------------------------------------------------------
algo_levels    <- c("DA", "EADAM", "TTC")
agg$algo       <- factor(agg$algo, levels = algo_levels)
algo_colors    <- c(DA = "#185FA5", EADAM = "#A32D2D", TTC = "#3B6D11")
algo_linetypes <- c(DA = "solid",   EADAM = "dashed",  TTC = "dotted")
algo_shapes    <- c(DA = 16,        EADAM = 15,        TTC = 17)

theme_base <- theme_minimal(base_size = 15, base_family = plot_font) +
  theme(legend.position = "bottom",
        legend.box.spacing = unit(0, "pt"),
        panel.grid.major = element_blank(),
        panel.grid.minor = element_blank(),
        axis.line = element_line(color = "black", linewidth = 0.5),
        axis.ticks = element_line(color = "black", linewidth = 0.5),
        axis.ticks.length = unit(3, "pt"),
        text = element_text(family = plot_font, color = "black"),
        axis.text = element_text(color = "black"),
        axis.title = element_text(color = "black"),
        legend.text = element_text(color = "black"))

# ---- Panel 1: share of students reassigned ---------------------------------
p_left <- ggplot()
if (nrow(ribbon_data) > 0) {
  p_left <- p_left + geom_ribbon(
    data = ribbon_data,
    aes(x = k, ymin = pct_switchers_DA, ymax = eff_mean_switch,
        fill = "Efficiency gap"),
    alpha = 0.55)
}
p_left <- p_left +
  geom_line(data = agg,
            aes(x = k, y = pct_switchers, color = algo, linetype = algo),
            linewidth = 0.7) +
  geom_point(data = agg,
             aes(x = k, y = pct_switchers, color = algo, shape = algo),
             size = 2) +
  scale_color_manual(values = algo_colors, name = NULL) +
  scale_linetype_manual(values = algo_linetypes, name = NULL) +
  scale_shape_manual(values = algo_shapes, name = NULL) +
  scale_fill_manual(values = c("Efficiency gap" = "#C0DD97"), name = NULL) +
  scale_x_continuous(breaks = ks) +
  scale_y_continuous(labels = function(x) paste0(x, "%")) +
  labs(x = "Days between runs",
       y = "Share of school switchers") +
  theme_base

# ---- Panel 2: share of 1st-choice switchers --------------------------------
p_right <- ggplot()
if (nrow(ribbon_data) > 0) {
  p_right <- p_right + geom_ribbon(
    data = ribbon_data,
    aes(x = k, ymin = pct_first_pref_DA, ymax = eff_mean_first,
        fill = "Efficiency gap"),
    alpha = 0.55)
}
p_right <- p_right +
  geom_line(data = agg,
            aes(x = k, y = pct_first_pref, color = algo, linetype = algo),
            linewidth = 0.7) +
  geom_point(data = agg,
             aes(x = k, y = pct_first_pref, color = algo, shape = algo),
             size = 2) +
  scale_color_manual(values = algo_colors, name = NULL) +
  scale_linetype_manual(values = algo_linetypes, name = NULL) +
  scale_shape_manual(values = algo_shapes, name = NULL) +
  scale_fill_manual(values = c("Efficiency gap" = "#C0DD97"), name = NULL) +
  scale_x_continuous(breaks = ks) +
  scale_y_continuous(labels = function(x) paste0(x, "%")) +
  labs(x = "Days between runs",
       y = "Share of 1st choice switchers") +
  theme_base

combined <- p_left + p_right + plot_layout(guides = "collect") &
  theme(legend.position = "bottom")

# ---- Save figures -----------------------------------------------------------
png_path <- file.path(out_dir, "plot_k_sensitivity.png")
pdf_path <- file.path(out_dir, "plot_k_sensitivity.pdf")
if (use_ragg) {
  ggsave(png_path, combined, width = 11, height = 4.5, dpi = 300, device = ragg::agg_png)
} else {
  ggsave(png_path, combined, width = 11, height = 4.5, dpi = 300)
}
message("  wrote ", png_path)

pdf_written <- FALSE
tryCatch({
  suppressWarnings(
    ggsave(pdf_path, combined, width = 11, height = 4.5, device = cairo_pdf))
  if (file.exists(pdf_path)) {
    pdf_written <- TRUE
    message("  wrote ", pdf_path)
  }
}, error = function(e) {
  message("  PDF skipped (cairo_pdf unavailable): ", conditionMessage(e),
          ". Install XQuartz for PDF output, or rely on the PNG.")
})

# ---- LaTeX figure wrapper ---------------------------------------------------
n_iter_str <- if (!is.na(n_iterations)) as.character(n_iterations) else "?"
muni_str   <- if (!is.null(munis_meta) && length(munis_meta) > 0) {
  paste(munis_meta, collapse = ", ")
} else {
  "the simulated municipalities"
}

caption <- paste0(
  "Outcomes by run frequency (days between matching runs). ",
  "Left: share of school switchers. Right: share of switchers placed at ",
  "their first-choice school. Lines aggregate across ", muni_str,
  " using applicant weights, with means taken across ", n_iter_str,
  " Monte Carlo iterations. The shaded band marks the efficiency gap ",
  "between DA and the average of the two efficient mechanisms."
)

tex_path <- file.path(out_dir, "plot_k_sensitivity.tex")
writeLines(c(
  "\\begin{figure}[htbp]",
  "\\centering",
  "\\includegraphics[width=\\linewidth]{output/sum_k/plot_k_sensitivity.png}",
  paste0("\\caption{", caption, "}"),
  "\\label{fig:k_sensitivity}",
  "\\end{figure}"
), tex_path)
message("  wrote ", tex_path)

message("[plot_k_sensitivity] done")
