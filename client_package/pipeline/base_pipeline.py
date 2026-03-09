from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import numpy as np

class BasePipeline(ABC):
    """
    Abstract base class for all ingestion pipelines.
    Defines the contract for processing, embedding, and linking logic.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config

    @abstractmethod
    async def run_pipeline(self, filename: str, content: bytes, metadata: Optional[Dict[str, Any]] = None, status_callback=None):
        """
        Main entry point for the pipeline.
        """
        pass

    def calculate_semantic_edges(self, rows: List[Any], threshold: float = 0.9):
        """
        Shared logic for calculating semantic edges between knowledge rows.
        Assumes rows have an 'embedding' attribute and 'edge_ids' attribute.
        """
        valid_rows = [r for r in rows if r.embedding]
        if len(valid_rows) < 2:
            return

        try:
            # Stack embeddings: N x D
            matrix = np.array([r.embedding for r in valid_rows])
            
            # Normalize
            norm = np.linalg.norm(matrix, axis=1, keepdims=True)
            norm[norm == 0] = 1e-10
            normalized_matrix = matrix / norm
            
            # Compute similarity
            similarity = np.dot(normalized_matrix, normalized_matrix.T)
            
            count_links = 0
            for i in range(len(valid_rows)):
                matches = np.where(similarity[i] > threshold)[0]
                linked_ids = []
                for idx in matches:
                    if idx != i:
                        linked_ids.append(valid_rows[idx].id)
                
                if linked_ids:
                    if valid_rows[i].edge_ids is None:
                        valid_rows[i].edge_ids = []
                    valid_rows[i].edge_ids.extend(linked_ids)
                    count_links += len(linked_ids)
            
            print(f"🕸️  Created {count_links} semantic edges (threshold > {threshold})")
            
        except Exception as e:
            print(f"⚠️  Error calculating semantic edges: {e}")
