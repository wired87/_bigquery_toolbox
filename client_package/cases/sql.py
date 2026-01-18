
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
        
        # 3. Get Schemas
        await update_status("📖 Loading schemas...", "load_schema")
        schemas = {}
        for t in relevant_tables:
            try:
                if self.engine.bq_core:
                    # RAG Engine uses BQCore/BigQueryRAG
                    schemas[t] = await asyncio.to_thread(self.engine.bq_core.bq_get_table_schema, t)
                else:
                     schemas[t] = "Schema unavailable"
            except Exception:
                schemas[t] = "Schema unavailable"
            
        # 4. Generate SQL
        await update_status("🤖 Generating SQL query...", "generate_sql")
        prompt = prompts.get_sql_generation_prompt(
            user_input, 
            json.dumps(formatted_table_names, indent=2),
            json.dumps(schemas, indent=2)
        )
        
        if not self.engine.model:
             return {
                "intent": "query_sql_generation",
                "response_text": "⚠️ AI features unavailable (Auth Error). Cannot generate SQL."
            }

        response = await asyncio.wait_for(
            self.engine.model.generate_content_async(prompt),
            timeout=60.0
        )
        sql_query = response.text.replace("```sql", "").replace("```", "").strip()
        print(f"📝 Generated SQL: {sql_query}")
        
        # 5. Execute SQL
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
                self.engine.model.generate_content_async(answer_prompt),
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
