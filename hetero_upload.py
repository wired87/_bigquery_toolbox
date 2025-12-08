import networkx as nx
import numpy as np
import pandas as pd
import io
import torch
import asyncio
from google.cloud import bigquery
from gnn.embedder import get_embedder
from torch_geometric.data import HeteroData

from ggoogle import GCP_ID
from ggoogle.bq import BQ_DATASET_ID


class BigQueryHeteroGraphHandler:
    def __init__(self, dataset_id=None, embedding_dim=16):
        """Initializes the BigQuery graph handler with embedding capabilities."""
        self.pid = GCP_ID
        self.ds_id = dataset_id or BQ_DATASET_ID
        self.embedding_dim = embedding_dim
        self.hetero_data = HeteroData()
        self.node_id_mapping = {}  # Maps node IDs
        self.node_feature_mapping = {}  # Stores node attributes
        self.edge_feature_mapping = {}  # Stores edge attributes
        self.embedder = get_embedder()  # Pre-trained embedding model

        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

        #self.lock = asyncio.Lock()




    async def upload_graph(self, ):
        """
        Processes a NetworkX graph into hetero-data format with embeddings and uploads to BigQuery.
        """


        # Convert features to tensors
        await self.convert_node_features()
        await self.convert_edges_to_tensors()

        # Ensure tables exist
        self.ensure_table_exists("nodes")
        self.ensure_table_exists("EDGES")
        self.ensure_table_exists("graph_info")

        # Convert to DataFrames
        nodes_df = self.graph_to_nodes_df()
        edges_df = self.graph_to_edges_df()
        info_df = self.create_info_table()

        # Upload to BigQuery
        self.upload_dataframe_to_bq(nodes_df, "nodes")
        self.upload_dataframe_to_bq(edges_df, "EDGES")
        self.upload_dataframe_to_bq(info_df, "graph_info")

    async def process_nodes(self, graph):
        """Embeds node features and adds them to the HeteroData object."""
        print(f"📍 Processing {len(graph.nodes)} Nodes...")
        i = 0
        for node_id, attrs in graph.nodes(data=True):
            if i >= 10:
                break
            i +=1
            self.node_id_mapping[str(node_id)] = node_index = len(self.node_id_mapping) + 1  # Assign unique ID
            node_type = attrs.get("layer") or attrs.get("type")  # Ensure node_type is valid

            # Generate embeddings asynchronously
            node_features = await asyncio.gather(
                *[self.embed_process(k, v, self.node_feature_mapping) for k, v in attrs.items()]
            )  # holds embeds in 2 dim

            print("Node festures for ", node_id, "created")

            node_features = [torch.tensor(f, dtype=torch.float).unsqueeze(0) if isinstance(f, (list, np.ndarray)) else f
                             for f in node_features]

            # Ensure all tensors have the same shape
            node_features = torch.cat(node_features, dim=0) if node_features else torch.zeros((1, self.embedding_dim))

            # Add to HeteroData safely
            async with self.lock:
                if node_type not in self.hetero_data:
                    self.hetero_data[node_type].x = node_features.unsqueeze(0)
                    self.hetero_data[node_type].node_id = torch.tensor([node_index], dtype=torch.long)
                else:
                    self.hetero_data[node_type].x = torch.cat(
                        [self.hetero_data[node_type].x, node_features.unsqueeze(0)], dim=0)
                    self.hetero_data[node_type].node_id = torch.cat([self.hetero_data[node_type].node_id,
                                                                     torch.tensor([node_index], dtype=torch.long)],
                                                                    dim=0)

    async def process_edges(self, graph):
        """Processes and assigns edge embeddings."""
        print(f"📍 Processing {len(graph.edges)} Edges...")
        i = 0
        for src, tgt, attrs in graph.edges(data=True):
            if i >= 10:
                break
            i += 1
            rel = attrs.get("relationship")
            if not rel:
                rel = attrs.get("relationship")
            edge_type = (graph.nodes[src].get("layer", "default"), rel, graph.nodes[tgt].get("layer", "default"))

            src_id = self.node_id_mapping.get(str(src), 0.0)
            dst_id = self.node_id_mapping.get(str(tgt), 0.0)

            edge_features = await asyncio.gather(
                *[self.embed_process(k, v, self.edge_feature_mapping) for k, v in attrs.items()]
            )
            edge_weight = torch.tensor([float(attrs.get("weight", 1.0))], dtype=torch.float)

            async with self.lock:
                if edge_type not in self.hetero_data:
                    self.hetero_data[edge_type].edge_index = ([], [])
                    self.hetero_data[edge_type].edge_weight = []
                    self.hetero_data[edge_type]["edge_attrs"] = []  # Keep as list

                new_edge = torch.tensor([[src_id], [dst_id]], dtype=torch.long)
                print("ADD EDGE: new_edge", new_edge, "\n edge_weight", edge_weight, "\n edge_features", edge_features)

                self.hetero_data[edge_type].edge_index[0].append(src_id)
                self.hetero_data[edge_type].edge_index[1].append(dst_id)

                self.hetero_data[edge_type].edge_weight.append(edge_weight)

                self.hetero_data[edge_type]["edge_attrs"].append(edge_features)

    async def embed_process(self, key, value, feature_dict):
        """Embeds node or edge attributes for ML processing."""
        if key not in feature_dict:
            feature_dict[key] = len(feature_dict)

        if isinstance(value, str):
            feature = await asyncio.to_thread(self.embedder.encode, value)
        elif isinstance(value, (int, float)):
            feature = np.array([value], dtype=np.float32)  # Convert to NumPy for consistency
        elif isinstance(value, list):
            feature = await asyncio.to_thread(self.embedder.encode, [str(v) for v in value])
        else:
            feature = np.zeros(self.embedding_dim)  # Ensure consistent shape

        # Convert NumPy arrays to PyTorch tensors and ensure 1D shape
        feature = torch.tensor(feature, dtype=torch.float).flatten()

        return feature

    async def convert_node_features(self):
        """Converts node feature lists into tensors."""
        for node_type in self.hetero_data.node_types:
            if isinstance(self.hetero_data[node_type].x, list):
                self.hetero_data[node_type].x = torch.stack(self.hetero_data[node_type].x)

    async def convert_edges_to_tensors(self):
        """Converts edge index and weight lists into tensors."""
        for edge_type in self.hetero_data.edge_types:
            self.hetero_data[edge_type].edge_index = torch.tensor(self.hetero_data[edge_type].edge_index, dtype=torch.long)
            self.hetero_data[edge_type].edge_weight = torch.stack(self.hetero_data[edge_type].edge_weight)
            self.hetero_data[edge_type].edge_attrs = torch.stack(self.hetero_data[edge_type].edge_attrs)

    def graph_to_nodes_df(self):
        """Converts HeteroData nodes to a Pandas DataFrame."""
        data = [{"id": node_id, "embedding": self.hetero_data[node_type].x[idx].tolist()}
                for node_type in self.hetero_data.node_types
                for idx, node_id in enumerate(self.hetero_data[node_type].node_id.tolist())]
        return pd.DataFrame(data)

    def graph_to_edges_df(self):
        """Converts HeteroData edges to a Pandas DataFrame."""
        data = [{"src": src, "tgt": tgt, "weight": weight.item()}
                for edge_type in self.hetero_data.edge_types
                for src, tgt, weight in zip(self.hetero_data[edge_type].edge_index[0].tolist(),
                                            self.hetero_data[edge_type].edge_index[1].tolist(),
                                            self.hetero_data[edge_type].edge_weight.tolist())]
        return pd.DataFrame(data)

    def create_info_table(self):
        """Creates an info table for node/edge mappings."""
        node_info = [{"node_id": k, "index": v} for k, v in self.node_id_mapping.items()]
        edge_info = [{"edge_attr": k, "index": v} for k, v in self.edge_feature_mapping.items()]
        return pd.DataFrame(node_info + edge_info)

    def ensure_table_exists(self, table_name):
        """Ensures a BigQuery table exists before uploading data."""
        table_ref = f"{self.pid}.{self.ds_id}.{table_name}"
        try:
            bigquery.Client().get_table(table_ref)
        except Exception:
            print(f"🟡 Table {table_name} not found, creating...")
            schema = [
                bigquery.SchemaField("id", "STRING"),
                bigquery.SchemaField("embedding", "STRING"),
            ] if table_name == "nodes" else [
                bigquery.SchemaField("src", "STRING"),
                bigquery.SchemaField("tgt", "STRING"),
                bigquery.SchemaField("weight", "FLOAT64"),
            ]
            bigquery.Client().create_table(bigquery.Table(table_ref, schema=schema))

    def upload_dataframe_to_bq(self, df, table_name):
        """Uploads a DataFrame to BigQuery."""
        client = bigquery.Client()
        job_config = bigquery.LoadJobConfig(source_format=bigquery.SourceFormat.CSV, write_disposition="WRITE_APPEND")
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        client.load_table_from_file(csv_buffer, f"{self.pid}.{self.ds_id}.{table_name}", job_config=job_config).result()
        print(f"✅ Uploaded {len(df)} rows to {table_name}.")
