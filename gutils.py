import logging
import uuid
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

@dataclass
class GNode:
    id: str
    tag: str
    content: str
    embedding: List[float] = field(default_factory=list)
    parent_id: Optional[str] = None
    children_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self):
        d = asdict(self)
        return d

class GUtils:
    def __init__(self, project_id: str):
        self.nodes: Dict[str, GNode] = {}
        self.edges: List[Dict[str, Any]] = []
        self.project_id = project_id
        self.embedding_model = None
        try:
            self.embedding_model = VertexAIEmbeddings(model_name="text-embedding-004", project=project_id)
        except Exception as e:
            print(f"Failed to initialize VertexAIEmbeddings: {e}")

    def create_node(self, tag_name: str, content: str, parent_id: Optional[str] = None, metadata: Dict = None, defer_embedding: bool = False) -> GNode:
        node_id = str(uuid.uuid4())
        
        embedding = []
        if not defer_embedding and self.embedding_model and content.strip():
            try:
                embedding = self.embedding_model.embed_query(content)
            except Exception as e:
                print(f"Embedding failed for node {node_id}: {e}")
        
        node = GNode(
            id=node_id,
            tag=tag_name,
            content=content,
            embedding=embedding,
            parent_id=parent_id,
            metadata=metadata or {}
        )
        
        self.nodes[node_id] = node
        
        if parent_id:
            # Hierarchy edge
            self.add_edge(parent_id, node_id, "hierarchy")
            if parent_id in self.nodes:
                self.nodes[parent_id].children_ids.append(node_id)
                
        return node

    def generate_embeddings_batched(self, batch_size: int = 10):
        """
        Generates embeddings for all nodes that don't have them yet, in batches.
        """
        if not self.embedding_model:
            print("No embedding model available, skipping batch generation.")
            return

        # Filter nodes that need embeddings and have content
        nodes_to_embed = [
            n for n in self.nodes.values() 
            if not n.embedding and n.content and n.content.strip()
        ]
        
        if not nodes_to_embed:
            return

        print(f"Generating embeddings for {len(nodes_to_embed)} nodes in batches of {batch_size}...")
        
        for i in range(0, len(nodes_to_embed), batch_size):
            batch = nodes_to_embed[i:i + batch_size]
            contents = [n.content for n in batch]
            ids = [n.id for n in batch]
            
            try:
                embeddings = self.embedding_model.embed_documents(contents)
                for node, emb in zip(batch, embeddings):
                    node.embedding = emb
            except Exception as e:
                print(f"Batch embedding failed for batch {i//batch_size}: {e}")

    def add_edge(self, source_id: str, target_id: str, edge_type: str, weight: float = 1.0):
        self.edges.append({
            "source": source_id,
            "target": target_id,
            "type": edge_type,
            "weight": weight
        })

    def process_similarity_edges(self, threshold: float = 0.96):
        """
        Add edges based on similarity search distance <= threshold.
        Distance assumed to be Cosine Distance (1 - similarity).
        """
        node_ids = list(self.nodes.keys())
        populated_nodes = [n for n in self.nodes.values() if n.embedding]
        
        if len(populated_nodes) < 2:
            return

        import numpy as np
        
        # Matrix op for speed if possible, but loop is fine for ingestion scripts usually
        # But O(N^2) might be slow for big PDFs.
        
        embeddings = np.array([n.embedding for n in populated_nodes])
        ids = [n.id for n in populated_nodes]
        
        # Normalize
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        # Avoid division by zero
        norms[norms == 0] = 1
        normalized = embeddings / norms
        
        # Cosine Similarity Matrix
        similarity_matrix = np.dot(normalized, normalized.T)
        
        # Distance = 1 - Similarity
        distance_matrix = 1 - similarity_matrix
        
        # Iterate upper triangle
        rows, cols = distance_matrix.shape
        for i in range(rows):
            for j in range(i + 1, cols):
                dist = distance_matrix[i, j]
                if dist <= threshold:
                    self.add_edge(ids[i], ids[j], "similarity", weight=float(dist))

    def visualize(self, output_file: str = "graph_visualization.html"):
        """
        Visualizes the graph using PyVis and saves to an HTML file.
        """
        try:
            from pyvis.network import Network
            
            net = Network(height="750px", width="100%", bgcolor="#222222", font_color="white")
            
            # Add Nodes
            for node_id, node in self.nodes.items():
                # Tooltip info
                title = f"Tag: {node.tag}\nFile: {node.metadata.get('file_name', 'N/A')}\nType: {node.metadata.get('file_type', 'N/A')}\nContent: {node.content[:50]}..."
                
                # Color based on file or tag?
                color = "#97c2fc" # Default blue
                if node.tag in ['p', 'span']: color = "#ffff00" # Yellow for text
                elif node.tag in ['div', 'body']: color = "#fb7e81" # Red for containers
                
                net.add_node(node_id, label=node.tag, title=title, color=color)
                
            # Add Edges
            for edge in self.edges:
                color = "#848484" # Default gray
                if edge['type'] == 'hierarchy': color = "#ffffff" # White for hierarchy
                elif edge['type'] == 'similarity': color = "#00ff00" # Green for similarity
                
                net.add_edge(edge['source'], edge['target'], title=f"{edge['type']} (w={edge['weight']:.2f})", color=color)
                
            net.save_graph(output_file)
            print(f"Graph visualization saved to {output_file}")
            
        except ImportError:
            print("PyVis not installed. Skipping visualization.")
        except Exception as e:
            print(f"Visualization failed: {e}")
