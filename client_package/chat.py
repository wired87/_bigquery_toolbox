import os

import vertexai
from google import genai
from google.genai.types import GenerateContentConfig, Retrieval, Tool, VertexRagStore
from vertexai import rag
from vertexai import generative_models


# -----------------------------------------------------------------------------
# Step 1: Initialize project and clients
# -----------------------------------------------------------------------------


def initialize_project_and_clients():
    """
    Initialize the Google Cloud project ID and create Vertex AI / GenAI clients.
    Uses GOOGLE_CLOUD_PROJECT env var if PROJECT_ID is not explicitly set.
    """
    # fmt: off
    PROJECT_ID = "[your-project-id]"  # @param {type: "string", placeholder: "[your-project-id]", isTemplate: true}
    # fmt: on
    if not PROJECT_ID or PROJECT_ID == "[your-project-id]":
        PROJECT_ID = str(os.environ.get("GOOGLE_CLOUD_PROJECT"))

    # See https://cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/rag-overview#supported-regions for location options.
    vertexai.init(project=PROJECT_ID, location="us-east1")
    client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")

    return PROJECT_ID, client


# -----------------------------------------------------------------------------
# Step 2: Create RAG corpus
# -----------------------------------------------------------------------------


def create_rag_corpus(project_id: str):
    """
    Create a RAG corpus with embedding model configuration.
    Currently supports Google first-party embedding models.
    """
    # fmt: off
    EMBEDDING_MODEL = "publishers/google/models/text-embedding-005"  # @param {type:"string", isTemplate: true}
    # fmt: on

    rag_corpus = rag.create_corpus(
        display_name="my-rag-corpus",
        backend_config=rag.RagVectorDbConfig(
            rag_embedding_model_config=rag.RagEmbeddingModelConfig(
                vertex_prediction_endpoint=rag.VertexPredictionEndpoint(
                    publisher_model=EMBEDDING_MODEL
                )
            )
        ),
    )

    return rag_corpus


# -----------------------------------------------------------------------------
# Step 3: Upload a single file to the RAG corpus
# -----------------------------------------------------------------------------


def upload_file_to_corpus(rag_corpus, file_path: str = "test.md"):
    """
    Upload a single file to the RAG corpus.
    """
    rag_file = rag.upload_file(
        corpus_name=rag_corpus.name,
        path=file_path,
        display_name=file_path,
        description="my test file",
    )
    return rag_file


# -----------------------------------------------------------------------------
# Step 4: Import files from GCS bucket
# -----------------------------------------------------------------------------


def import_files_from_gcs(rag_corpus, gcs_bucket: str | None = None):
    """
    Import files from a Google Cloud Storage bucket into the RAG corpus.
    Supports optional chunking configuration and rate limiting.
    """
    INPUT_GCS_BUCKET = (
        gcs_bucket
        or "gs://cloud-samples-data/gen-app-builder/search/alphabet-investor-pdfs/"
    )

    response = rag.import_files(
        corpus_name=rag_corpus.name,
        paths=[INPUT_GCS_BUCKET],
        # Optional
        transformation_config=rag.TransformationConfig(
            chunking_config=rag.ChunkingConfig(chunk_size=1024, chunk_overlap=100)
        ),
        max_embedding_requests_per_min=900,  # Optional
    )
    return response


# -----------------------------------------------------------------------------
# Step 5: Import files from Google Drive
# -----------------------------------------------------------------------------


def import_files_from_google_drive(rag_corpus, folder_id: str):
    """
    Import files from a Google Drive folder into the RAG corpus.
    Requires a valid Drive folder ID.
    """
    response = rag.import_files(
        corpus_name=rag_corpus.name,
        paths=[f"https://drive.google.com/drive/folders/{folder_id}"],
        # Optional
        transformation_config=rag.TransformationConfig(
            chunking_config=rag.ChunkingConfig(chunk_size=512, chunk_overlap=50)
        ),
    )
    return response


# -----------------------------------------------------------------------------
# Step 6: Direct context retrieval (query RAG without model)
# -----------------------------------------------------------------------------


def direct_retrieval_query(
    rag_corpus,
    query_text: str = "What is RAG and why it is helpful?",
    top_k: int = 10,
    vector_distance_threshold: float = 0.5,
):
    """
    Perform direct context retrieval from the RAG corpus.
    Returns relevant chunks without invoking a generative model.
    """
    response = rag.retrieval_query(
        rag_resources=[
            rag.RagResource(
                rag_corpus=rag_corpus.name,
                # Optional: supply IDs from `rag.list_files()`.
                # rag_file_ids=["rag-file-1", "rag-file-2", ...],
            )
        ],
        rag_retrieval_config=rag.RagRetrievalConfig(
            top_k=top_k,  # Optional
            filter=rag.Filter(
                vector_distance_threshold=vector_distance_threshold,  # Optional
            ),
        ),
        text=query_text,
    )
    return response


# -----------------------------------------------------------------------------
# Step 7: Create RAG retrieval tool for GenAI client
# -----------------------------------------------------------------------------


def create_rag_retrieval_tool(
    rag_corpus,
    similarity_top_k: int = 10,
    vector_distance_threshold: float = 0.5,
):
    """
    Create a Tool for the RAG corpus to use with the GenAI generate_content API.
    """
    rag_retrieval_tool = Tool(
        retrieval=Retrieval(
            vertex_rag_store=VertexRagStore(
                rag_corpora=[rag_corpus.name],
                similarity_top_k=similarity_top_k,
                vector_distance_threshold=vector_distance_threshold,
            )
        )
    )
    return rag_retrieval_tool


# -----------------------------------------------------------------------------
# Step 8: Generate content with Gemini model using RAG
# -----------------------------------------------------------------------------


def generate_content_with_gemini(
    client,
    rag_retrieval_tool,
    prompt: str = "What is RAG?",
    model_id: str = "gemini-3-flash-preview",
):
    """
    Generate content using the Gemini model with RAG retrieval.
    Displays the response as Markdown.
    """
    response = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config=GenerateContentConfig(tools=[rag_retrieval_tool]),
    )
    return response


# -----------------------------------------------------------------------------
# Step 9: Create RAG retrieval tool for Vertex generative models (e.g. Llama)
# -----------------------------------------------------------------------------


def create_rag_tool_for_generative_model(
    rag_corpus,
    top_k: int = 10,
    vector_distance_threshold: float = 0.5,
):
    """
    Load RAG retrieval tool for use with Vertex generative models (e.g. Llama).
    """
    rag_retrieval_tool = generative_models.Tool.from_retrieval(
        retrieval=rag.Retrieval(
            source=rag.VertexRagStore(
                rag_resources=[rag.RagResource(rag_corpus=rag_corpus.name)],
                rag_retrieval_config=rag.RagRetrievalConfig(
                    top_k=top_k,  # Optional
                    filter=rag.Filter(
                        vector_distance_threshold=vector_distance_threshold,  # Optional
                    ),
                ),
            ),
        ),
    )
    return rag_retrieval_tool


# -----------------------------------------------------------------------------
# Step 10: Generate content with Llama model using RAG
# -----------------------------------------------------------------------------


def generate_content_with_llama(
    rag_retrieval_tool,
    prompt: str = "What is RAG?",
    endpoint_path: str = "projects/{project}/locations/{location}/endpoints/{endpoint_resource_id}",
):
    """
    Generate content using a self-deployed Llama model with RAG retrieval.
    Requires a deployed Llama endpoint.
    """
    llama_model = generative_models.GenerativeModel(
        endpoint_path,
        tools=[rag_retrieval_tool],
    )
    response = llama_model.generate_content(prompt)
    return response


# -----------------------------------------------------------------------------
# Main execution flow (example usage)
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # Step 1: Initialize
    project_id, client = initialize_project_and_clients()

    # Step 2: Create corpus
    rag_corpus = create_rag_corpus(project_id)

    # Step 3: Upload file
    upload_file_to_corpus(rag_corpus)

    # Step 4: Import from GCS (optional)
    # import_files_from_gcs(rag_corpus)

    # Step 5: Import from Drive (optional - requires folder_id)
    # import_files_from_google_drive(rag_corpus, folder_id="{folder_id}")

    # Step 6: Direct retrieval
    retrieval_response = direct_retrieval_query(rag_corpus)
    print(retrieval_response)

    # Step 7 & 8: Gemini with RAG
    rag_tool = create_rag_retrieval_tool(rag_corpus)
    generate_content_with_gemini(client, rag_tool)

    # Step 9 & 10: Llama with RAG (requires deployed endpoint)
    # llama_rag_tool = create_rag_tool_for_generative_model(rag_corpus)
    # generate_content_with_llama(llama_rag_tool)
