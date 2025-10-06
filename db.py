import os
import psycopg2
import logging
from dotenv import load_dotenv
from typing import Any

from copy import deepcopy

logger = logging.getLogger(__name__)

load_dotenv()


class DataBase:
    def __init__(self):
        self.conn_params: dict[str, Any] = {
            "user": os.environ.get("USER"),
            "host": os.environ.get("HOST", "127.0.0.1"),
            "password": os.environ.get("PASSWORD"),
            "port": 5432,
        }

    def _get_connection(self, database: str = None, autocommit: bool = False) -> Any:
        """Helper method to create a connection with optional database and autocommit."""
        params = deepcopy(self.conn_params)
        if database:
            params["database"] = database
        conn = psycopg2.connect(**params)
        conn.autocommit = autocommit
        return conn
