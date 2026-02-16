import asyncio
from typing import Optional
import vertexai
from vertexai.generative_models import GenerativeModel

class CategoryHandler:
    def __init__(self, project_id: str, location: str = "us-central1"):
        self.generative_model = None
        try:
            vertexai.init(project=project_id, location=location)
            self.generative_model = GenerativeModel("gemini-1.5-flash-001")
            print("✅ Vertex AI Generative Model (gemini-1.5-flash-001) initialized for CategoryHandler.")
        except Exception as e:
            print(f"⚠️  Failed to init Vertex AI for CategoryHandler: {e}")

    async def generate_category(self, filename: str, content_snippet: str) -> str:
        """
        Uses LLM to generate a category name for the file based on its name and content snippet.
        """
        if not self.generative_model:
            return "Uncategorized"

        try:
            prompt = f"""
            Analyze the following file information and assign a short, descriptive category name (1-3 words).
            
            File Name: {filename}
            Content Snippet: {content_snippet[:500]}...
            
            Examples of categories: Legal Contract, Financial Report, Technical Spec, Meeting Notes, Invoice, Resume.
            
            Category:
            """
            
            response = await asyncio.to_thread(self.generative_model.generate_content, prompt)
            category = response.text.strip()
            # Basic cleanup
            category = category.replace("Category:", "").strip()
            return category if category else "Uncategorized"
        except Exception as e:
            print(f"⚠️  Error generating category: {e}")
            return "Uncategorized"
