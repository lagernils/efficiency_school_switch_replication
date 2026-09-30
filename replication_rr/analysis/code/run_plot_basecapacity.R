# =============================================================================
# run_plot_basecapacity.R
#
# Renders the % Switchers vs % extra seats figure (linear x-axis with a shaded
# ribbon between DA and the mean of EADAM/TTC) from the lite-mode CSVs that
# masterfile.py produces.
#
# Two parameterisations are supported, selected by `uses_overcapacity` in the
# metadata file:
#
#   TRUE  (replication_rr) -- reads overcapacity(_demandprop)/run_x<N>.csv,
#         where N is already the percentage of additional seats per active
#         student. The x-axis is therefore a genuine continuous percentage.
#   FALSE (original, replication) -- reads basecapacity(_demandprop)/run_p<N>.csv,
#         where N is a whole number of extra seats per school, and the x-axis
#         percentage has to be derived from diagnostic_unique_programs.csv.
#
# Inputs:
#   build/output/plot_meta_basecapacity.json -- run-context metadata written by
#                                  masterfile.py: the parameterisation, the
#                                  ADD_CAPACITIES_BY_DEMAND flag (which
#                                  picks the input subfolder and the output
#                                  suffix), and the x-axis ranges to render.
#   <subfolder>/run_{x,p}<N>.csv               -- one per loop value.
#   <subfolder>/diagnostic_unique_programs.csv -- per (muni, year, grade).
#
# Outputs (under <project>/analysis/output/sum_{over,base}capacity/). Every
# filename carries two suffixes so nothing collides: the allocation mode
# ("_uniform" or "_demandprop") and the x-axis range variant ("_full" for
# 0-100%, "_zoom" for 0-50%, where the efficiency gap actually closes):
#   plot_overcapacity_<mode>_<variant>.pdf -- the figure (vector, for LaTeX).
#   plot_overcapacity_<mode>_<variant>.png -- raster copy.
#   plot_overcapacity_<mode>_<variant>.tex -- LaTeX \begin{figure} wrapper with
#                                  a caption capturing k, n_iterations, the
#                                  municipalities, the priority scheme and the
#                                  EADAM consent setting.
# and, when CREATE_FIRSTCHOICE_CAPACITY_PLOT is TRUE, the matching
#   plot_overcapacity_firstchoice_panel_<mode>_<variant>.{png,pdf,tex}
# =============================================================================

# ---- First-choice extension toggle ------------------------------------------
# If TRUE, also builds a combined two-panel figure -- share of switchers (left,
# identical to the main plot_basecapacity.png) and share of 1st-choice
# switchers (right, new) -- mirroring Figure 1's two-panel layout, so the
# referee can see directly whether the capacity-slack pattern also holds for
# 1st-choice placements. Uses columns already present in run_p*.csv
# (pct_first_pref_switchers_mean/_std), so no Python rerun is needed either
# way. Intended for the referee response, not necessarily the main text.
CREATE_FIRSTCHOICE_CAPACITY_PLOT <- TRUE

suppressPackageStartupMessages({
  library(readr)
  library(dplyr)
  library(tidyr)
  library(ggplot2)
})
have_jsonlite <- requireNamespace("jsonlite", quietly = TRUE)

`%||%` <- function(a, b) if (is.null(a) || (length(a) == 1 && is.na(a))) b else a

# ---- Locate project root (mirrors run_analysis.R) ---------------------------
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

# ---- Read plot_meta_basecapacity.json (optional; powers the caption AND the
# capacity-allocation mode below). Lives one level above the
# basecapacity/basecapacity_demandprop subfolders so it can be read before
# we've picked which of those two subfolders to use.
meta <- list()
meta_path <- file.path(project_root, "build", "output", "plot_meta_basecapacity.json")
if (have_jsonlite && file.exists(meta_path)) {
  meta <- tryCatch(jsonlite::fromJSON(meta_path), error = function(e) list())
} else {
  message("[plot_basecapacity] ", meta_path, " not found -- defaulting to ",
          "ADD_CAPACITIES_BY_DEMAND=FALSE (uniform) and generic caption fields. ",
          "This file is only written by masterfile.py's run_basecapacity_loop() ",
          "(run_loop_over_basecapacity_bool=TRUE), not by its standard mode.")
}
focal_k       <- as.integer(meta$loop_fixed_k       %||% 90)
n_iterations  <- as.integer(meta$n_iterations       %||% NA)
munis         <- meta$list_of_municipalities        %||% NULL
random_priors <- isTRUE(meta$random_priorities      %||% NA)
full_consent  <- isTRUE(meta$full_consent_bool      %||% NA)
base_caps     <- meta$base_capacity_values          %||% NULL
project_name  <- meta$project                       %||% basename(project_root)

# Which capacity-allocation counterfactual to read/plot. Auto-detected
# from meta (written by masterfile.py) rather than a manual toggle, so this
# always matches whichever Python run actually produced the cached CSVs.
demand_mode  <- isTRUE(meta$ADD_CAPACITIES_BY_DEMAND %||% FALSE)
fname_suffix <- if (demand_mode) "_demandprop" else "_uniform"

# Which parameterisation produced the cached CSVs (see the header comment).
overcap_mode <- isTRUE(meta$uses_overcapacity %||% FALSE)
dir_stem     <- if (overcap_mode) "overcapacity" else "basecapacity"
run_pattern  <- if (overcap_mode) "^run_x[0-9.]+\\.csv$" else "^run_p\\d+\\.csv$"
x_col        <- if (overcap_mode) "overcapacity_pct" else "base_capacity"

# X-axis upper bounds to render, one figure per entry. Named list: the name
# becomes the filename variant suffix, the value is the right-hand x limit.
plot_ranges <- meta$overcapacity_plot_ranges %||% list(full = 100, zoom = 50)
plot_ranges <- as.list(plot_ranges)
if (!overcap_mode) plot_ranges <- list(full = Inf)   # legacy: single figure

basecap_dir <- file.path(project_root, "build", "output",
                          paste0(dir_stem, if (demand_mode) "_demandprop" else ""))
out_dir     <- file.path(project_root, "analysis", "output", paste0("sum_", dir_stem))
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

if (!dir.exists(basecap_dir)) {
  message("[plot_basecapacity] ", basecap_dir, " does not exist -- nothing to plot.")
  quit(status = 0)
}

# ---- Read run CSVs ----------------------------------------------------------
run_files <- list.files(basecap_dir, pattern = run_pattern, full.names = TRUE)
if (length(run_files) == 0) {
  message("[plot_basecapacity] no files matching ", run_pattern, " in ",
          basecap_dir, " -- nothing to plot.")
  quit(status = 0)
}
runs <- do.call(rbind, lapply(run_files, function(f)
  suppressMessages(read_csv(f, show_col_types = FALSE))))
if (!(x_col %in% names(runs))) {
  message("[plot_basecapacity] expected column '", x_col, "' in the run CSVs but ",
          "found: ", paste(names(runs), collapse = ", "),
          ". The cached CSVs were written by a different version of main.py -- ",
          "clear ", basecap_dir, " and rerun.")
  quit(status = 0)
}
runs$x_val <- as.numeric(runs[[x_col]])

# ---- Read diagnostic_unique_programs.csv ------------------------------------
diag_path <- file.path(basecap_dir, "diagnostic_unique_programs.csv")
diag <- if (file.exists(diag_path))
  suppressMessages(read_csv(diag_path, show_col_types = FALSE)) else NULL
total_unique <- if (!is.null(diag)) sum(diag$n_unique_programs) else NA_real_
total_stud   <- if (!is.null(diag)) sum(diag$n_students)        else NA_real_

# ---- Aggregate across municipalities (applicant-weighted) -------------------
# pct_first_pref is only aggregated (and only required to exist in run_p*.csv)
# when CREATE_FIRSTCHOICE_CAPACITY_PLOT is actually TRUE, so leaving the
# toggle off never depends on that column being present -- e.g. if this
# script is ever pointed at older/differently-shaped CSVs.
if (CREATE_FIRSTCHOICE_CAPACITY_PLOT && !("pct_first_pref_switchers_mean" %in% names(runs))) {
  message("[plot_basecapacity] CREATE_FIRSTCHOICE_CAPACITY_PLOT is TRUE but run_p*.csv ",
          "files have no pct_first_pref_switchers_mean column -- skipping the 1st-choice panel.")
  CREATE_FIRSTCHOICE_CAPACITY_PLOT <- FALSE
}

if (CREATE_FIRSTCHOICE_CAPACITY_PLOT) {
  agg <- runs |>
    dplyr::filter(k == focal_k) |>
    dplyr::group_by(algo, x_val) |>
    dplyr::summarise(
      pct_switchers = sum(pct_switchers_mean * total_students_mean) /
                       sum(total_students_mean),
      pct_first_pref = sum(pct_first_pref_switchers_mean * total_students_mean) /
                       sum(total_students_mean),
      .groups = "drop"
    )
} else {
  agg <- runs |>
    dplyr::filter(k == focal_k) |>
    dplyr::group_by(algo, x_val) |>
    dplyr::summarise(
      pct_switchers = sum(pct_switchers_mean * total_students_mean) /
                       sum(total_students_mean),
      .groups = "drop"
    )
}

# ---- X-axis layout ----------------------------------------------------------
# On the overcapacity parameterisation x_val IS the percentage of additional
# seats, so it is plotted directly on a continuous axis. On the legacy
# base_capacity parameterisation the percentage has to be derived from the
# unique-programs diagnostic, and the runs are placed at equally spaced
# discrete tick positions because their magnitudes are far apart.
if (overcap_mode) {
  agg$x_plot <- agg$x_val
  x_label    <- "Additional seats per active student"
} else {
  agg$pct_overcap <- if (!is.na(total_unique) && !is.na(total_stud) && total_stud > 0) {
    total_unique * agg$x_val * 100 / total_stud
  } else {
    NA_real_
  }
  plot_max_bc <- as.numeric(meta$plot_max_base_capacity %||% 4)
  agg <- agg[agg$x_val <= plot_max_bc, ]
  ordered_bcs   <- sort(unique(agg$x_val))
  agg$x_plot    <- match(agg$x_val, ordered_bcs)
  x_tick_labels <- if (all(!is.na(agg$pct_overcap)))
    sprintf("%.0f%%", total_unique * ordered_bcs * 100 / total_stud)
  else as.character(ordered_bcs)
  x_label <- if (all(!is.na(agg$pct_overcap)))
    "Additional seats per applicant"
  else "Base capacity (extra net seats per school per year)"
}

# ---- Pivot wide to compute the shaded ribbon (lower = DA, upper = efficient_mean)
wide <- agg |>
  dplyr::select(algo, x_val, x_plot, pct_switchers) |>
  tidyr::pivot_wider(names_from = algo, values_from = pct_switchers) |>
  dplyr::arrange(x_val)
if (!all(c("DA", "EADAM", "TTC") %in% names(wide))) {
  message("[plot_basecapacity] need DA, EADAM and TTC rows; have ",
          paste(names(wide), collapse = ", "), " -- skipping ribbon.")
  wide$efficient_mean <- NA_real_
  ribbon_data <- wide[FALSE, ]
} else {
  wide$efficient_mean <- (wide$EADAM + wide$TTC) / 2
  ribbon_data <- wide
}

# ---- Same pivot/ribbon, for the 1st-choice panel ----------------------------
if (CREATE_FIRSTCHOICE_CAPACITY_PLOT) {
  wide_fc <- agg |>
    dplyr::select(algo, x_val, x_plot, pct_first_pref) |>
    tidyr::pivot_wider(names_from = algo, values_from = pct_first_pref) |>
    dplyr::arrange(x_val)
  if (!all(c("DA", "EADAM", "TTC") %in% names(wide_fc))) {
    message("[plot_basecapacity] (1st-choice panel) need DA, EADAM and TTC rows; have ",
            paste(names(wide_fc), collapse = ", "), " -- skipping ribbon.")
    wide_fc$efficient_mean <- NA_real_
    ribbon_data_fc <- wide_fc[FALSE, ]
  } else {
    wide_fc$efficient_mean <- (wide_fc$EADAM + wide_fc$TTC) / 2
    ribbon_data_fc <- wide_fc
  }
}

# ---- Build the plot ---------------------------------------------------------
algo_levels    <- c("DA", "EADAM", "TTC")
agg$algo       <- factor(agg$algo, levels = algo_levels)
algo_colors    <- c(DA = "#185FA5", EADAM = "#A32D2D", TTC = "#3B6D11")
algo_linetypes <- c(DA = "solid",   EADAM = "dashed",  TTC = "dotted")
algo_shapes    <- c(DA = 16,        EADAM = 15,        TTC = 17)

# ---- Font and device setup --------------------------------------------------
# Use Times New Roman to match the paper's LaTeX font (\renewcommand{\rmdefault}{ptm}
# = PostScript Times). Preferred path: ragg + systemfonts (discovers Times via
# system font dirs). Fallback path: showtext + sysfonts.
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

# Fallback: register Times through showtext if ragg/systemfonts didn't find it.
if (!use_custom_font &&
    requireNamespace("showtext", quietly = TRUE) &&
    requireNamespace("sysfonts", quietly = TRUE)) {
  ff <- tryCatch(sysfonts::font_files(), error = function(e) NULL)
  if (!is.null(ff) && nrow(ff) > 0) {
    rx <- function(p) grepl(p, ff$file, ignore.case = TRUE)
    # Match "Times New Roman.ttf", "Times-Roman.*", or "Times.ttf"/"Times.ttc"
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
      }, error = function(e) {
        message("[plot_basecapacity] font registration failed: ", conditionMessage(e))
      })
    }
  }
}

if (!use_custom_font) {
  message("[plot_basecapacity] Times New Roman unavailable; using default font. ",
          "Install ragg (recommended) or showtext/sysfonts, and ensure ",
          "Times New Roman is on the system.")
  plot_font <- ""
}

# ---- Shared theme -----------------------------------------------------------
base_theme <- theme_minimal(base_size = 13, base_family = plot_font) +
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

# ---- Panel builder ----------------------------------------------------------
# `xmax` is the right-hand x limit; points beyond it are dropped BEFORE the
# scale is applied, so nothing is silently clipped by ggplot (the previous
# version's hard y limit of 85 quietly discarded every run above that level).
# The y axis runs 0-`Y_AXIS_MAX`% with 20-point ticks. It is raised to 100
# automatically if any plotted value would otherwise fall outside it -- under
# demand-proportional allocation the curves reach ~96% at x=100%, and a fixed
# 80 would clip them. Never lower this without that guard: a hard y limit that
# is smaller than the data makes ggplot DROP the offending points silently,
# which is exactly how the earlier limit of 85 hid every run above that level.
Y_AXIS_MAX <- 80

make_panel <- function(dat, ribbon, yvar, ylab, xmax) {
  dat    <- dat[dat$x_plot <= xmax, , drop = FALSE]
  ribbon <- ribbon[ribbon$x_plot <= xmax, , drop = FALSE]

  ymax <- Y_AXIS_MAX
  if (nrow(dat) > 0 && max(dat[[yvar]], na.rm = TRUE) > ymax) {
    ymax <- 100
    message("[plot_basecapacity] data exceed Y_AXIS_MAX (", Y_AXIS_MAX,
            "); y axis widened to 100 for this panel so nothing is clipped.")
  }

  g <- ggplot()
  if (nrow(ribbon) > 0) {
    g <- g + geom_ribbon(
      data = ribbon,
      aes(x = x_plot, ymin = DA, ymax = efficient_mean, fill = "Efficiency gap"),
      alpha = 0.35)
  }
  g <- g +
    geom_line(data = dat,
              aes(x = x_plot, y = .data[[yvar]], color = algo, linetype = algo),
              linewidth = 0.7) +
    geom_point(data = dat,
               aes(x = x_plot, y = .data[[yvar]], color = algo, shape = algo),
               size = 2) +
    scale_color_manual(values = algo_colors, name = NULL) +
    scale_linetype_manual(values = algo_linetypes, name = NULL) +
    scale_shape_manual(values = algo_shapes, name = NULL) +
    scale_fill_manual(values = c("Efficiency gap" = "#C0DD97"), name = NULL) +
    scale_y_continuous(limits = c(0, ymax), breaks = seq(0, ymax, by = 20),
                       labels = function(v) paste0(v, "%"))

  if (overcap_mode) {
    step <- if (xmax <= 50) 10 else 20
    g <- g + scale_x_continuous(limits = c(0, xmax),
                                breaks = seq(0, xmax, by = step),
                                labels = function(v) paste0(v, "%"),
                                expand = expansion(mult = c(0.02, 0.02)))
  } else {
    g <- g + scale_x_continuous(breaks = seq_along(ordered_bcs),
                                labels = x_tick_labels,
                                expand = expansion(mult = c(0.02, 0.02)))
  }
  g + labs(x = x_label, y = ylab) + base_theme
}

have_patchwork <- requireNamespace("patchwork", quietly = TRUE)
if (CREATE_FIRSTCHOICE_CAPACITY_PLOT && !have_patchwork) {
  message("[plot_basecapacity] CREATE_FIRSTCHOICE_CAPACITY_PLOT is TRUE but the ",
          "'patchwork' package is not installed -- skipping the combined figure. ",
          "Install with: install.packages('patchwork').")
}
if (CREATE_FIRSTCHOICE_CAPACITY_PLOT && have_patchwork) {
  suppressPackageStartupMessages(library(patchwork))
}

n_iter_str <- if (!is.na(n_iterations)) as.character(n_iterations) else "?"

save_figure <- function(plot_obj, stem, width, height) {
  png_path <- file.path(out_dir, paste0(stem, ".png"))
  pdf_path <- file.path(out_dir, paste0(stem, ".pdf"))
  if (use_ragg) {
    ggsave(png_path, plot_obj, width = width, height = height, dpi = 300,
           device = ragg::agg_png)
  } else {
    ggsave(png_path, plot_obj, width = width, height = height, dpi = 300)
  }
  message("  wrote ", png_path)
  tryCatch({
    suppressWarnings(
      ggsave(pdf_path, plot_obj, width = width, height = height, device = cairo_pdf))
    if (file.exists(pdf_path)) message("  wrote ", pdf_path)
  }, error = function(e) {
    message("  PDF skipped (cairo_pdf unavailable): ", conditionMessage(e),
            ". Install XQuartz for PDF output, or rely on the PNG.")
  })
}

# ---- Render one figure (and one 1st-choice panel) per x-axis range ----------
for (variant in names(plot_ranges)) {
  xmax    <- as.numeric(plot_ranges[[variant]])
  suffix  <- paste0(fname_suffix, if (overcap_mode) paste0("_", variant) else "")
  range_note <- if (overcap_mode && is.finite(xmax))
    paste0(" Horizontal axis truncated at ", xmax, "\\%.") else ""

  p <- make_panel(agg, ribbon_data, "pct_switchers",
                  "Share of school switchers", xmax)
  save_figure(p, paste0("plot_", dir_stem, suffix), width = 6, height = 4)

  caption <- paste0(
    "The DA-to-efficient gap closes as capacity expands. ",
    "Share of students reassigned at $k=", focal_k, "$ days for DA, EADAM and TTC, ",
    if (demand_mode)
      "when additional seats are allocated in proportion to the number of students ranking each program. "
    else
      "when additional seats are added evenly across programs. ",
    "Horizontal axis: additional seats as a percentage of active students ",
    "(= total extra seats $\\div$ active students).", range_note, " ",
    "Means across ", n_iter_str, " Monte Carlo iterations, ",
    "applicant-weighted across the six municipalities; ",
    "shaded band: gap between DA and the EADAM/TTC mean."
  )
  tex_path <- file.path(out_dir, paste0("plot_", dir_stem, suffix, ".tex"))
  writeLines(c(
    "\\begin{figure}[htbp]",
    "\\centering",
    paste0("\\includegraphics[width=0.85\\linewidth]{output/sum_", dir_stem,
           "/plot_", dir_stem, suffix, ".png}"),
    paste0("\\caption{", caption, "}"),
    paste0("\\label{fig:", dir_stem, suffix, "}"),
    "\\end{figure}"
  ), tex_path)
  message("  wrote ", tex_path)

  # ---- 1st-choice two-panel figure ------------------------------------------
  if (CREATE_FIRSTCHOICE_CAPACITY_PLOT && have_patchwork) {
    p_first <- make_panel(agg, ribbon_data_fc, "pct_first_pref",
                          "Share of 1st choice switchers", xmax)
    combined_fc <- p + p_first + patchwork::plot_layout(guides = "collect") &
      theme(legend.position = "bottom")

    fc_stem <- paste0("plot_", dir_stem, "_firstchoice_panel", suffix)
    save_figure(combined_fc, fc_stem, width = 11, height = 4.5)

    fc_caption <- paste0(
      "As Figure~\\ref{fig:", dir_stem, suffix, "}, but showing the ",
      "share of switchers placed at their first-choice school (right panel) ",
      "alongside the original share-of-switchers panel (left), at $k=", focal_k,
      "$ days.", range_note
    )
    fc_tex_path <- file.path(out_dir, paste0(fc_stem, ".tex"))
    writeLines(c(
      "\\begin{figure}[htbp]",
      "\\centering",
      paste0("\\includegraphics[width=\\linewidth]{output/sum_", dir_stem, "/", fc_stem, ".png}"),
      paste0("\\caption{", fc_caption, "}"),
      paste0("\\label{fig:", dir_stem, "_firstchoice_rr", suffix, "}"),
      "\\end{figure}"
    ), fc_tex_path)
    message("  wrote ", fc_tex_path)
  }
}

message("[plot_basecapacity] done")
