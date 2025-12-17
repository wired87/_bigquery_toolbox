from google.cloud import bigquery
from typing import Set, List
import logging
import time

logger = logging.getLogger(__name__)

class SecurityManager:
    def __init__(self, project_id: str, dataset_id: str):
        self.bq_client = bigquery.Client(project=project_id)
        self.table_ref = f"{project_id}.{dataset_id}.blocked_ips"
        self.blocked_ips: Set[str] = set()
        self.last_refresh = 0
        self.refresh_interval = 60 # Refresh every minute

    def _ensure_table(self):
        """Creates blocked_ips table if not exists"""
        schema = [
            bigquery.SchemaField("ip_address", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("reason", "STRING"),
            bigquery.SchemaField("blocked_at", "TIMESTAMP"),
        ]
        try:
            self.bq_client.get_table(self.table_ref)
        except Exception:
            table = bigquery.Table(self.table_ref, schema=schema)
            self.bq_client.create_table(table)
            logger.info(f"Created table {self.table_ref}")

    def refresh_blacklist(self):
        """Fetches blocked IPs from BigQuery"""
        if time.time() - self.last_refresh < self.refresh_interval:
            return

        try:
            self._ensure_table()
            query = f"SELECT ip_address FROM `{self.table_ref}`"
            rows = self.bq_client.query(query).result()
            self.blocked_ips = {row.ip_address for row in rows}
            self.last_refresh = time.time()
            logger.info(f"Refreshed blacklist: {len(self.blocked_ips)} IPs blocked.")
        except Exception as e:
            logger.error(f"Failed to refresh blacklist: {e}")

    def is_blocked(self, ip: str) -> bool:
        self.refresh_blacklist()
        return ip in self.blocked_ips

    def block_ip(self, ip: str, reason: str = "Manual Block"):
        """Blocks an IP permanently"""
        try:
            query = f"""
            INSERT INTO `{self.table_ref}` (ip_address, reason, blocked_at)
            VALUES ('{ip}', '{reason}', CURRENT_TIMESTAMP())
            """
            self.bq_client.query(query).result()
            self.blocked_ips.add(ip)
            logger.info(f"Blocked IP: {ip}")
        except Exception as e:
            logger.error(f"Failed to block IP {ip}: {e}")
