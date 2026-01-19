
import logging
import asyncio
import json
from typing import Dict, Any
from error_handler import log_exception
import prompts

logger = logging.getLogger(__name__)

class SQLHandler:
    def __init__(self, engine):
        self.engine = engine

    async def handle(self, user_input: str, status_callback=None) -> Dict[str, Any]:
        """
        Handles the workflow for 'query_sql_generation' intent.
        Delegates to handle_sql_generation logic.
        """
        async def update_status(message, step=""):
            if status_callback: await status_callback(message, step)

        result = {
            "intent": "query_sql_generation",
            "response_text": "",
            "source_citation": None,
            "traceability": None
        }

        print("📊 Starting SQL generation workflow")
        await update_status("📊 Analyzing database schema...", "schema")
        
        try:
            sql_result = await self.handle_sql_generation(user_input, status_callback)
            result.update(sql_result)
            print(f"✅ SQL generation completed")
            
        except Exception as e:
            log_exception(e, "SQL Generation")
            await update_status(f"❌ SQL generation failed", "error")
            result["response_text"] = f"SQL generation failed: {str(e)}"

        return result

    async def handle_sql_generation(self, user_input: str, status_callback=None) -> Dict[str, Any]:
        """
        Handles the SQL generation workflow.
        Moved from engine.py
        """
        async def update_status(message: str, step: str = ""):
            if status_callback: await status_callback(message, step)
        
        # 1. Select Tables (Forced to KB)
        relevant_tables = ["KB"]
        formatted_table_names = [f"{self.engine.pid}.{self.engine.current_dataset_id}.KB"]
        await update_status(f"✅ Selected knowledge base: {formatted_table_names[0]}", "tables_selected")
        
        # 3. Get Schemas & Metadata
        await update_status("📖 Loading schemas and metadata...", "load_schema")
        schemas = {}
        metadata = {}
        for t in relevant_tables:
            try:
                if self.engine.bq_core:
                    # RAG Engine uses BQCore/BigQueryRAG
                    schemas[t] = await asyncio.to_thread(self.engine.bq_core.bq_get_detailed_table_schema, t)
                    
                    # Fetch extra metadata (rows, size, etc.)
                    meta = await asyncio.to_thread(self.engine.get_table_metadata, t)
                    metadata[t] = meta
                else:
                     schemas[t] = "Schema unavailable"
                     metadata[t] = "Metadata unavailable"
            except Exception:
                schemas[t] = "Schema unavailable"
                metadata[t] = "Metadata unavailable"
            
        # 4. Generate SQL
        await update_status("🤖 Generating SQL query...", "generate_sql")
        
        # Combine schema and metadata for the prompt
        context_data = {
            "schemas": schemas,
            "table_metadata": metadata
        }
        
        prompt = prompts.get_sql_generation_prompt(
            user_input, 
            json.dumps(formatted_table_names, indent=2),
            json.dumps(context_data, indent=2) # Pass full context
        )
        
        if not self.engine.model:
             return {
                "intent": "query_sql_generation",
                "response_text": "⚠️ AI features unavailable (Auth Error). Cannot generate SQL."
            }

        async def generate_and_validate(attempt=1, last_error=None):
            if attempt > 2: # Max retries
                raise Exception(f"Failed to generate valid SQL after 2 attempts. Last error: {last_error}")

            current_prompt = prompt
            if last_error:
                current_prompt += f"\n\nprevious_sql_error: {last_error}\nFIX THE SQL."

            response = await asyncio.wait_for(
                asyncio.to_thread(self.engine.model.generate_content, current_prompt),
                timeout=60.0
            )
            raw_sql = response.text.replace("```sql", "").replace("```", "").strip()
            
            # Extract SQL if CoT is present (look for last SELECT statement if mixed with text, or basic cleanup)
            # Simple heuristic: if "SELECT" is not at start, try to find it. 
            # But the prompt asks for "Return ONLY the raw SQL string".
            # If CoT is followed, the model might output text then SQL. 
            # Let's trust the "Then, write the SQL" instruction but handle potential chatter.
            sql_query = raw_sql
            if "SELECT" in raw_sql:
                idx = raw_sql.find("SELECT")
                sql_query = raw_sql[idx:]
            
            print(f"📝 Generated SQL (Attempt {attempt}): {sql_query}")

            # DRY RUN VALIDATION
            await update_status(f"🧪 Dry run validation (Attempt {attempt})...", "dry_run")
            try:
                # Use bq_client (raw google client) for dry run
                job_config = self.engine.bqclient.query_defaults if hasattr(self.engine.bqclient, 'query_defaults') else None
                # Create a dry run config
                from google.cloud import bigquery
                dry_run_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
                
                # Check query validity
                self.engine.bqclient.query(sql_query, job_config=dry_run_config)
                print("✅ Dry run successful.")
                return sql_query
            except Exception as e:
                print(f"❌ Dry run failed: {e}")
                return await generate_and_validate(attempt+1, str(e))

        # Start Generation Loop
        try:
             sql_query = await generate_and_validate()
        except Exception as e:
             return {
                "intent": "query_sql_generation",
                "response_text": f"Could not generate valid SQL: {e}"
            }
        
        # 5. Execute SQL (Real Run)
        await update_status("⚡ Executing query on BigQuery...", "execute_query")
        try:
             # Use engine.bq_core to run query
            query_result = await asyncio.to_thread(
                self.engine.bq_core.run_query,
                sql_query,
                conv_to_dict=True
            )
            
            # 6. Generate Final Answer
            await update_status("💭 Formulating answer...", "formulate_answer")
            answer_prompt = prompts.get_natural_answer_prompt(
                user_input,
                sql_query,
                json.dumps(query_result, default=str)
            )
            answer_response = await asyncio.wait_for(
                asyncio.to_thread(self.engine.model.generate_content, answer_prompt),
                timeout=60.0
            )
            
            return {
                "intent": "query_sql_generation",
                "response_text": answer_response.text,
                "source_citation": f"BigQuery SQL on {', '.join(relevant_tables)}",
                "query_result": query_result,
                "traceability": {
                    "original_question": user_input,
                    "sql_query": sql_query,
                    "result_preview": str(query_result)[:500]
                }
            }
        except Exception as e:
            return {
                "intent": "query_sql_generation",
                "response_text": f"Failed to execute SQL: {e}",
                "traceability": {
                    "original_question": user_input,
                    "sql_query": sql_query,
                    "error": str(e)
                }
            }
