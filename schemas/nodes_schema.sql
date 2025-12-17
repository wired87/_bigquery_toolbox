-- Schema for Knowledge Nodes (Data Categorization Optimized)
CREATE TABLE IF NOT EXISTS `nodes` (
  id STRING NOT NULL,
  content STRING,
  source_file STRING,
  chunk_type STRING,
  parent_id STRING,
  page INT64,
  category STRING, -- New Categorization Field
  tags ARRAY<STRING>, -- New Tagging System
  ingested_at TIMESTAMP,
  embed ARRAY<FLOAT64> -- Vector Embedding
);
