
import unittest
import numpy as np
from client_package.processor.main import FileProcessorFacade # Just for imports if needed, but we test logic directly
# We need to import the method or class. The method is in ProductionIngestionPipeline
# But extracting it to a standalone test might be easier if we mock the class.

import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ingestion_pipeline import KnowledgeRow, ProductionIngestionPipeline, PipelineConfig

class TestSemanticLinking(unittest.TestCase):
    def test_calculate_semantic_edges(self):
        # Setup specific embeddings
        # A and B are identical (sim = 1.0)
        # C is orthogonal (sim = 0.0)
        # D is close to A (sim > 0.9)
        
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [1.0, 0.0, 0.0] 
        vec_c = [0.0, 1.0, 0.0]
        vec_d = [0.95, 0.2, 0.0] # approx match to A
        
        rows = [
            KnowledgeRow(id="A", file_id="f1", file_type="pdf", content="A", metadata="{}", embedding=vec_a),
            KnowledgeRow(id="B", file_id="f1", file_type="pdf", content="B", metadata="{}", embedding=vec_b),
            KnowledgeRow(id="C", file_id="f1", file_type="pdf", content="C", metadata="{}", embedding=vec_c),
            KnowledgeRow(id="D", file_id="f1", file_type="pdf", content="D", metadata="{}", embedding=vec_d),
        ]
        
        config = PipelineConfig(dataset_id="test", table_id="nodes")
        pipeline = ProductionIngestionPipeline(config)
        
        # Test logic
        pipeline._calculate_semantic_edges(rows, threshold=0.9)
        
        # Check A
        # A should link to B and D (and maybe self if not filtered, but code filters self)
        ids_a = set(rows[0].edge_ids)
        print(f"Edges for A: {ids_a}")
        self.assertIn("B", ids_a)
        self.assertIn("D", ids_a)
        self.assertNotIn("A", ids_a) # No self loop
        self.assertNotIn("C", ids_a) # No orthogonal
        
        # Check C
        ids_c = set(rows[2].edge_ids)
        self.assertEqual(len(ids_c), 0) # C matches none

if __name__ == '__main__':
    unittest.main()
