# =============================================================================
# run_analysis.R  -- master orchestrator
#
# Calls each sub-script in turn:
#   make_tables.R              -> writes tables 1-4 under analysis/output/
#   run_plot_k_sensitivity.R   -> writes the k-sensitivity figure under
#                                 analysis/output/sum_k/
#   run_plot_basecapacity.R    -> writes the base-capacity figure under
#                                 analysis/output/sum_basecapacity/
#
# Each sub-script is run in its own Rscript subprocess so that quit() and
# package state stay isolated. Each script handles missing-data cases
# gracefully (skips quietly when the inputs it needs are not present), so
# this orchestrator works in both standard mode (per-muni CSVs present)
# and base-capacity-loop mode (run_x*.csv present, per-muni CSVs absent).
# =============================================================================

script_dir <- tryCatch(
  dirname(rstudioapi::getSourceEditorContext()$path),
  error = function(e) {
    args <- commandArgs(trailingOnly = FALSE)
    file_arg <- grep("^--file=", args, value = TRUE)
    if (length(file_arg)) dirname(normalizePath(sub("^--file=", "", file_arg)))
    else getwd()
  }
)

run_subscript <- function(name) {
  path <- file.path(script_dir, name)
  if (!file.exists(path)) {
    message("[run_analysis] ", name, " not found, skipping")
    return(invisible(NULL))
  }
  message("\n[run_analysis] running ", name, " ...")
  status <- system2("Rscript", args = shQuote(path))
  if (status != 0) {
    message("[run_analysis] ", name, " exited with status ", status)
  } else {
    message("[run_analysis] ", name, " completed")
  }
  invisible(status)
}

run_subscript("make_tables.R")
run_subscript("run_plot_k_sensitivity.R")
run_subscript("run_plot_basecapacity.R")

message("\n[run_analysis] all sub-scripts done")
