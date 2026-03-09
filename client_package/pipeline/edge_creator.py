import asyncio
from typing import List, Dict, Any
from google.cloud import bigquery
import numpy as np

class EdgeCreator:
    def __init__(self, bq_client: bigquery.Client, table_ref: str):
        self.bq_client = bq_client
        self.table_ref = table_ref

    async def run_full_table_edge_creation(self, batch_size: int = 100, threshold: float = 0.9):
        """
        Fetches all IDs from the table and runs the edge creation workflow in batches.
        """
        print(f"🚀 Starting full table edge creation for {self.table_ref}...")
        
        # 1. Fetch all IDs
        try:
            query = f"SELECT id FROM `{self.table_ref}`"
            query_job = self.bq_client.query(query)
            results = await asyncio.to_thread(query_job.result)
            all_ids = [row.id for row in results]
            print(f"📋 Found {len(all_ids)} total rows.")
        except Exception as e:
            print(f"❌ Error fetching all IDs: {e}")
            return

        # 2. Process in batches
        total_processed = 0
        for i in range(0, len(all_ids), batch_size):
            batch_ids = all_ids[i : i + batch_size]
            print(f"🔄 Processing batch {i // batch_size + 1} ({len(batch_ids)} rows)...")
            await self.create_edges(batch_ids, threshold)
            total_processed += len(batch_ids)
            
        print(f"✅ Completed edge creation for {total_processed} rows.")

    async def create_edges(self, row_ids: List[str], threshold: float = 0.9):
        """
        For each row_id, performs a similarity search over the entire table.
        Collects IDs of rows with similarity > threshold.
        Upserts the edge_ids list back to BigQuery.
        """
        if not row_ids:
            return

        # print(f"🕸️  Starting edge creation for {len(row_ids)} rows (threshold > {threshold})...")
        
        # 1. Fetch embeddings for the target rows
        target_rows = await self._fetch_embeddings(row_ids)
        if not target_rows:
            print("⚠️  No embeddings found for target rows.")
            return

        # 2. Perform similarity search for each row
        updates = []
        for row in target_rows:
            row_id = row["id"]
            embedding = row["embedding"]
            
            if not embedding:
                continue

            similar_ids = await self._find_similar_ids(row_id, embedding, threshold)
            
            if similar_ids:
                updates.append({"id": row_id, "edge_ids": similar_ids})

        # 3. Upsert updates
        if updates:
            await self._upsert_edges(updates)
            print(f"   -> Updated edges for {len(updates)} rows.")
        else:
            print("   -> No new edges found in this batch.")

    async def _fetch_embeddings(self, row_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetches id and embedding for the given row_ids."""
        # Construct a safe query with parameters
        query = f"""
            SELECT id, embedding
            FROM `{self.table_ref}`
            WHERE id IN UNNEST(@ids)
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("ids", "STRING", row_ids)
            ]
        )
        
        try:
            query_job = self.bq_client.query(query, job_config=job_config)
            results = await asyncio.to_thread(query_job.result)
            return [{"id": row.id, "embedding": row.embedding} for row in results]
        except Exception as e:
            print(f"❌ Error fetching embeddings: {e}")
            return []

    async def _find_similar_ids(self, source_id: str, embedding: List[float], threshold: float) -> List[str]:
        """
        Performs a vector search using cosine similarity.
        Note: This uses a brute-force exact search or vector index search depending on BQ optimization.
        For large tables, ensure a vector index exists.
        """
        # Using ML.DISTANCE or COSINE_DISTANCE
        # Assuming embedding column is FLOAT64 REPEATED
        
        query = f"""
            SELECT id
            FROM `{self.table_ref}`
            WHERE id != @source_id
            AND ML.DISTANCE(embedding, @target_embedding, 'COSINE') < (1 - @threshold)
            LIMIT 50
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("source_id", "STRING", source_id),
                bigquery.ArrayQueryParameter("target_embedding", "FLOAT64", embedding),
                bigquery.ScalarQueryParameter("threshold", "FLOAT64", threshold)
            ]
        )

        try:
            query_job = self.bq_client.query(query, job_config=job_config)
            results = await asyncio.to_thread(query_job.result)
            return [row.id for row in results]
        except Exception as e:
            print(f"❌ Error finding similar rows for {source_id}: {e}")
            return []

    async def _upsert_edges(self, updates: List[Dict[str, Any]]):
        """
        Updates the edge_ids column for the specified rows.
        Since BQ doesn't support direct partial updates easily without DML,
        we use a MERGE statement for efficiency or UPDATE.
        """
        
        query = f"""
            MERGE `{self.table_ref}` T
            USING UNNEST(@updates) AS S
            ON T.id = S.id
            WHEN MATCHED THEN
                UPDATE SET edge_ids = ARRAY_CONCAT(IFNULL(T.edge_ids, []), S.new_edges)
        """
        
        # Correctly structure the parameters for Array of Structs
        struct_updates = [
            (u["id"], u["edge_ids"]) 
            for u in updates
        ]
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter(
                    "updates",
                    bigquery.StructQueryParameterType(
                        bigquery.ScalarQueryParameterType("STRING", name="id"),
                        bigquery.ArrayQueryParameterType(bigquery.ScalarQueryParameterType("STRING"), name="new_edges")
                    ),
                    struct_updates
                )
            ]
        )

        try:
            query_job = self.bq_client.query(query, job_config=job_config)
            await asyncio.to_thread(query_job.result)
        except Exception as e:
            print(f"❌ Error upserting edges: {e}")

if __name__ == "__main__":
    # Test execution
    async def main():
        client = bigquery.Client()
        # Using the KB table of the h_e_com dataset as requested
        table_ref = f"{client.project}.h_e_com.KB"
        
        creator = EdgeCreator(client, table_ref)
        await creator.run_full_table_edge_creation(batch_size=50, threshold=0.85)

    asyncio.run(main())
