args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 4) {
    stop("Usage: deseq2_tximport.R <sample_sheet.csv> <tx2gene.csv> <output_dir> <reference_level>")
}

if (!requireNamespace("tximport", quietly = TRUE)) {
    stop("The Bioconductor package 'tximport' is required.")
}
if (!requireNamespace("DESeq2", quietly = TRUE)) {
    stop("The Bioconductor package 'DESeq2' is required.")
}

sample_sheet <- read.csv(args[[1]], stringsAsFactors = FALSE, check.names = FALSE)
tx2gene <- read.csv(args[[2]], stringsAsFactors = FALSE, check.names = FALSE)
output_dir <- args[[3]]
reference_level <- args[[4]]

required_sample_columns <- c("sample_id", "condition", "quant_dir")
required_mapping_columns <- c("transcript_id", "gene_id")
if (!all(required_sample_columns %in% names(sample_sheet))) {
    stop("Sample sheet must contain sample_id, condition, and quant_dir columns.")
}
if (!all(required_mapping_columns %in% names(tx2gene))) {
    stop("Transcript mapping must contain transcript_id and gene_id columns.")
}
if (anyDuplicated(sample_sheet$sample_id)) {
    stop("Sample IDs must be unique.")
}
if (anyDuplicated(tx2gene$transcript_id)) {
    stop("Each transcript_id must appear only once in the transcript mapping.")
}
if (anyNA(sample_sheet[, required_sample_columns]) ||
    any(trimws(as.matrix(sample_sheet[, required_sample_columns])) == "")) {
    stop("Sample sheet fields must not be empty.")
}
if (anyNA(tx2gene[, required_mapping_columns]) ||
    any(trimws(as.matrix(tx2gene[, required_mapping_columns])) == "")) {
    stop("Transcript mapping fields must not be empty.")
}

conditions <- unique(sample_sheet$condition)
if (length(conditions) != 2 || !reference_level %in% conditions) {
    stop("Exactly two conditions are required, and reference_level must match one of them.")
}
replicates <- table(sample_sheet$condition)
if (any(replicates < 2)) {
    stop("At least two biological replicates per condition are required.")
}

quant_files <- file.path(sample_sheet$quant_dir, "quant.sf")
if (!all(file.exists(quant_files))) {
    stop("Every quant_dir must contain a quant.sf file.")
}
names(quant_files) <- sample_sheet$sample_id

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
txi <- tximport::tximport(
    quant_files,
    type = "salmon",
    tx2gene = tx2gene[, required_mapping_columns],
    countsFromAbundance = "no",
    dropInfReps = TRUE
)

other_level <- setdiff(conditions, reference_level)
sample_sheet$condition <- factor(sample_sheet$condition, levels = c(reference_level, other_level))
rownames(sample_sheet) <- sample_sheet$sample_id
dds <- DESeq2::DESeqDataSetFromTximport(
    txi,
    colData = sample_sheet,
    design = ~ condition
)
dds <- dds[rowSums(DESeq2::counts(dds)) >= 10, ]
if (nrow(dds) == 0) {
    stop("No genes remain after filtering for at least 10 total counts.")
}
dds <- DESeq2::DESeq(dds)

result <- DESeq2::results(dds, contrast = c("condition", other_level, reference_level))
result_table <- as.data.frame(result)
result_table$gene_id <- rownames(result_table)
result_table <- result_table[, c("gene_id", "baseMean", "log2FoldChange", "lfcSE", "stat", "pvalue", "padj")]
utils::write.csv(result_table, file.path(output_dir, "deseq2_results.csv"), row.names = FALSE)

normalized_counts <- as.data.frame(DESeq2::counts(dds, normalized = TRUE))
normalized_counts$gene_id <- rownames(normalized_counts)
normalized_counts <- normalized_counts[, c("gene_id", sample_sheet$sample_id)]
utils::write.csv(normalized_counts, file.path(output_dir, "normalized_counts.csv"), row.names = FALSE)
