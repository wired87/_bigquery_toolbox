"""
Authentication Manager for BigQuery Toolbox
Handles user authentication using BigQuery tables in the 'IDB' dataset.
"""
import re
from google.cloud import bigquery
from google.api_core.exceptions import NotFound
from typing import Optional, Dict, Any

class AuthManager:
    """
    Manages user authentication by creating and validating user-specific Datasets.
    One Dataset per User.
    """
    
    def __init__(self, bq_client: bigquery.Client, project_id: str):
        self.bq_client = bq_client
        self.project_id = project_id

    def normalize_email_to_user_id(self, email: str) -> str:
        """
        Convert email to normalized user_id (Dataset ID).
        Lowercase, strip, replace [^a-z0-9] with _.
        """
        norm_email = email.lower().strip()
        # User specified: only a-z, 0-9 allowed, rest is _
        user_id = re.sub(r'[^a-z0-9]', '_', norm_email)
        return user_id

    def create_user_dataset(self, email: str, password: str, user_id: str) -> Dict[str, Any]:
        """
        Create a new user dataset with 'kb' and 'metadata' tables.
        Store credentials in Dataset Labels.
        """
        dataset_ref = f"{self.project_id}.{user_id}"
        
        try:
            # 1. Create Dataset
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "US"
            
            # Store password in labels (limited chars: lowercase, digits, _, -)
            # We use hex encoding for the hash
            encoded_pw = self._encode_password_for_label(password)
            
            # Labels keys/values must be lowercase, digits, _ or -
            dataset.labels = {
                "password": encoded_pw,
                "email": self.normalize_email_to_user_id(email)[:63] # Truncate if too long for val
            }
            
            self.bq_client.create_dataset(dataset, exists_ok=False)
            
            # 2. Create 'kb' table (Knowledge Base)
            # We create a minimal schema, Pipeline will evolve it
            kb_ref = f"{dataset_ref}.kb"
            kb_schema = [
                bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("content", "STRING"),
                bigquery.SchemaField("created_at", "TIMESTAMP")
            ]
            kb_table = bigquery.Table(kb_ref, schema=kb_schema)
            self.bq_client.create_table(kb_table)
            
            # 3. Create 'metadata' table
            meta_ref = f"{dataset_ref}.metadata"
            meta_schema = [
                bigquery.SchemaField("key", "STRING"),
                bigquery.SchemaField("value", "STRING"),
                bigquery.SchemaField("updated_at", "TIMESTAMP")
            ]
            meta_table = bigquery.Table(meta_ref, schema=meta_schema)
            self.bq_client.create_table(meta_table)
            
            return {
                "success": True,
                "dataset_id": user_id,
                "table_id": "kb", # Standard table name
                "auth_state": "created_and_authenticated",
                "message": f"✅ Dataset created for {email}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"❌ Error creating dataset: {e}",
                "error": str(e)
            }

    def authenticate_user(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate by checking Dataset existence and labels.
        """
        user_id = self.normalize_email_to_user_id(email)
        dataset_ref = f"{self.project_id}.{user_id}"
        
        try:
            # Check Dataset
            dataset = self.bq_client.get_dataset(dataset_ref)
            
            # Dataset exists, check password label
            stored_pw = dataset.labels.get("password", "")
            provided_pw = self._encode_password_for_label(password)
            
            if stored_pw == provided_pw:
                return {
                    "success": True,
                    "dataset_id": user_id,
                    "table_id": "kb",
                    "auth_state": "authenticated",
                    "message": f"✅ Authenticated as {email}"
                }
            else:
                return {
                    "success": False,
                    "auth_state": "authentication_failed",
                    "message": "❌ Invalid password"
                }

        except NotFound:
            # Dataset does not exist -> Create it
            print(f"Dataset {user_id} not found. Registering new user...")
            return self.create_user_dataset(email, password, user_id)
            
        except Exception as e:
             return {
                "success": False,
                "message": f"❌ Auth Error: {e}",
                "error": str(e)
            }

    def _encode_password_for_label(self, password: str) -> str:
        import hashlib
        # User requested "hashed password". 
        # Labels accept [a-z0-9_-]. Hex digest is safe.
        hash_object = hashlib.sha256(password.encode())
        return hash_object.hexdigest()[:63] # Limit length just in case
