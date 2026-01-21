# Query Process Improvement Plan

This document outlines a strategic roadmap for elevating the query engine to a production-ready, highly professional standard. The goal is to ensure seamless, high-value answers through optimized query techniques.

## 1. Query Understanding & Refinement (The "Input" Layer)

Before searching or generating SQL, we must strictly understand user intent.

### 1.1 Query Expansion & Decomposition
**Problem:** Users often ask vague or multi-faceted questions.
**Solution:** Implement an intermediate LLM step to:
- **Decompose:** Break complex questions into sub-questions (e.g., "Compare sales in 2023 vs 2024" -> "Get sales 2023", "Get sales 2024", "Calculate difference").
- **Expand:** Generate synonyms or related terms for vector search (e.g., "HR docs" -> "Human Resources policies", "Employee handbook").
- **Technique:** Use `prompts.get_query_expansion_prompt` to generate 3-5 variations of the input for better retrieval coverage.

### 1.2 Hypothetical Document Embeddings (HyDE)
**Technique:** Instead of embedding the *question*, generate a hypothetical *answer* and embed that. This often matches the vector space of the actual documents better than the question does.

## 2. Advanced Retrieval Strategies (The "Search" Layer)

Improving how we find relevant chunks in BigQuery.

### 2.1 Optimized Hybrid Search (Keyword + Vector)
**Current:** We likely use a simple vector search or basic hybrid.
**Improvement:** Implement **Reciprocal Rank Fusion (RRF)**.
- Run Vector Search (Semantic).
- Run Keyword Search (Exact Match/BM25 via BigQuery Search Index).
- Combine results using RRF scores to prioritize items that appear in both lists.

### 2.2 Re-Ranking (The Precision Layer)
**Problem:** Vector search returns top-k based on cosine similarity, which can be noisy.
**Solution:** Fetch a larger candidate set (e.g., Top 50) and use a specialized **Cross-Encoder Model** (or high-fidelity LLM pass) to re-rank specific to the user's query.
- *Action:* Keep top 10 re-ranked items for the context window.

### 2.3 Metadata Filtering
**Technique:** Use the "Source" or "Date" entities extracted during the Understanding phase to apply hard filters on BigQuery `WHERE` clauses (e.g., `WHERE file_type = 'pdf'` or `WHERE ingested_at > '2024-01-01'`).

## 3. Production-Grade SQL Generation (The "Structured" Layer)

Ensuring SQL queries are accurate, efficient, and executable.

### 3.1 Schema Pruning & Injection
**Problem:** Passing the entire schema for all tables consumes context tokens and confuses the model.
**Solution:**
- **Dynamic Selection:** selecting *only* tables relevant to the query (already partially done).
- **Enriched Schema:** Pass specific "Allowed Column Values" for categorical fields (e.g., `status` IN ['active', 'closed']) to prevent hallucinated filters.

### 3.2 Chain-of-Thought (CoT) SQL Generation
**Improvement:** Update the prompt to force the LLM to explanations *before* the code.
- "First, identify the tables needed..."
- "Second, determine the join conditions..."
- "Third, write the SQL."
- This drastically reduces syntax errors and logic flaws.

### 3.3 Self-Correction Loop
**Workflow:**
1. Generate SQL.
2. **Dry Run:** Use BigQuery `DRY RUN` to check validity and cost.
3. If Error: Feed error message back to LLM -> "Fix this SQL error: [Error]".
4. Execute.

## 4. Synthesis & Response (The "Output" Layer)

### 4.1 Answer Grading & Citation
**Requirement:** Answers must be grounded in facts.
- **Verification:** The LLM must cite specific chunks (e.g., `[Source: file.pdf]`).
- **Hallucination Check:** If the retrieved context is insufficient, the system *must* explicitly state "I don't have enough information" rather than guessing.

### 4.2 Formatting & Tone
- Ensure high-contrast, professional markdown formatting.
- Use tables for structured data results.

---

## 5. Immediate Implementation Steps

1.  **Modify `prompts.py`**:
    *   Add `get_query_expansion_prompt` (Ph 1.1).
    *   Update `get_sql_generation_prompt` to include CoT instructions (Ph 3.2).
    *   Refine `get_natural_answer_prompt` for better citations (Ph 4.1).

2.  **Update `rag/core.py` / `engine.py`**:
    *   Implement the expansion loop before case dispatch.
    *   Refine the SQL execution block to include the `DRY RUN` check (Ph 3.3).

3.  **Refine Ingestion (`ingestion_pipeline.py`)**:
    *   Ensure metadata (dates, authors) is extracted robustly to support filtering (Ph 2.3).
