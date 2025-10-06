import os
import psycopg2
from typing import Any
import json
from psycopg2 import OperationalError
import logging
from psycopg2 import sql

from copy import deepcopy

logger = logging.getLogger(__name__)


class DataBase:
    def __init__(self):
        self.conn_params: dict[str, Any] = {
            "user": os.environ.get("USER"),
            "host": os.environ.get("HOST", "127.0.0.1"),
            "password": os.environ.get("PASSWORD"),
            "port": 5432,
        }

    def _get_connection(
        self,
        database: str = None,
        autocommit: bool = False,
    ) -> Any:
        """Helper method to create a connection with optional database and autocommit."""
        params = deepcopy(self.conn_params)
        if database:
            params["database"] = database
        conn = psycopg2.connect(**params)
        conn.autocommit = autocommit
        return conn

    def create_db(self) -> None:
        """Create the chat database if it doesn't exist."""
        try:
            conn = self._get_connection(database="postgres", autocommit=True)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT datname 
                FROM pg_database 
                WHERE datname = %s
            """,
                ("chat",),
            )

            if not cursor.fetchone():
                # Create database if it doesn't exist
                cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier("chat"))
                )

        except psycopg2.OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def create_user_table(self) -> None:
        """Create the user table with necessary columns."""
        try:
            conn = self._get_connection(database="chat", autocommit=True)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY NOT NULL,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    is_admin BOOLEAN NOT NULL,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    pv JSONB
                )
            """)
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def create_group_table(self) -> None:
        try:
            conn = self._get_connection(database="chat", autocommit=True)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    id SERIAL PRIMARY KEY NOT NULL,
                    name VARCHAR(50) UNIQUE NOT NULL
                )
            """)
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def create_group_chat_table(self):
        try:
            conn = self._get_connection(database="chat", autocommit=True)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS group_chat (
                    id SERIAL PRIMARY KEY NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
                    message TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def create_group_members_table(self) -> None:
        """Create the group_members table to track memberships."""
        try:
            conn = self._get_connection(database="chat", autocommit=True)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS group_members (
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE SET NULL,
                    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
                    PRIMARY KEY (user_id, group_id)
                )
            """)
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def get_user_id(self, username: str) -> int | None:
        """Get user ID by username."""
        try:
            conn = self._get_connection(database="chat")
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            result = cursor.fetchone()
            return result[0] if result else None
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def get_group_id(self, name: str) -> int | None:
        """Get group ID by name."""
        try:
            conn = self._get_connection(database="chat")
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM groups WHERE name = %s", (name,))
            result = cursor.fetchone()
            return result[0] if result else None
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def is_user_admin(self, username: str) -> bool:
        """Check if a user is admin by username."""
        try:
            conn = self._get_connection(database="chat")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT is_admin FROM users WHERE username = %s", (username,)
            )
            result = cursor.fetchone()
            return result[0] if result else False
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def add_member_to_group(self, user_id: int, group_id: int) -> bool:
        """Add a user to a group (idempotent)."""
        try:
            conn = self._get_connection(database="chat", autocommit=True)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO group_members (user_id, group_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, group_id) DO NOTHING
            """,
                (user_id, group_id),
            )
            return cursor.rowcount > 0
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def remove_member_from_group(self, user_id: int, group_id: int) -> bool:
        """Remove a user from a group."""
        try:
            conn = self._get_connection(database="chat", autocommit=True)
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM group_members
                WHERE user_id = %s AND group_id = %s
            """,
                (user_id, group_id),
            )
            return cursor.rowcount > 0
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def get_all_groups_with_members(self) -> dict[str, set[str]]:
        """Load all groups with their member usernames."""
        groups = {}
        try:
            conn = self._get_connection(database="chat")
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM groups")

            # Refactor the `for` loop using `map` function
            group_names = cursor.fetchall()
            groups = dict(map(lambda name: (name[0], set()), group_names))

            cursor.execute("""
                SELECT g.name, u.username
                FROM group_members gm
                JOIN groups g ON gm.group_id = g.id
                JOIN users u ON gm.user_id = u.id
            """)
            for group_name, uname in cursor.fetchall():
                groups[group_name].add(uname)
            return groups
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def get_group_messages(self, group_id: int, limit: int = 50) -> list[dict]:
        """Get recent messages for a group (for history fetching)."""
        try:
            conn = self._get_connection(database="chat")
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT u.username, gc.message, gc.timestamp
                FROM group_chat gc
                JOIN users u ON gc.user_id = u.id
                WHERE gc.group_id = %s
                ORDER BY gc.timestamp DESC
                LIMIT %s
            """,
                (group_id, limit),
            )
            return [
                {"from": row[0], "data": row[1], "timestamp": row[2]}
                for row in cursor.fetchall()
            ]
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def add_user(self, username: str, is_admin: bool = False) -> int:
        """Add a new user to the users table and return the user ID."""
        try:
            conn = self._get_connection(database="chat", autocommit=True)
            cursor = conn.cursor()

            cursor.execute(
                """SELECT id FROM users WHERE username = %s""",
                (username,),
            )
            existing_user = cursor.fetchone()

            if existing_user is not None:
                return existing_user[0]

            cursor.execute("""SELECT COUNT(*) FROM users""")
            user_count = cursor.fetchone()[0]

            if user_count == 0:
                is_admin = True

            cursor.execute(
                """INSERT INTO users (username, is_admin) VALUES (%s, %s) RETURNING id""",
                (username, is_admin),
            )
            new_user_id = cursor.fetchone()[0]

            return new_user_id
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def add_group(self, name: str) -> int:
        """Add a new group to the groups table and return the group ID."""
        try:
            conn = self._get_connection(database="chat", autocommit=True)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO groups (name) VALUES (%s) RETURNING id", (name,)
            )
            group_id = cursor.fetchone()[0]
            return group_id
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def add_user_to_group_chat(
        self,
        user_id: int,
        group_id: int,
        message: str,
    ) -> int:
        """Add a new message from a user to a group chat and return the message ID."""
        try:
            conn = self._get_connection(database="chat", autocommit=True)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO group_chat (user_id, group_id, message) VALUES (%s, %s, %s) RETURNING id",
                (user_id, group_id, message),
            )
            message_id = cursor.fetchone()[0]
            return message_id
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def add_message_to_group_chat(
        self,
        user_id: int,
        group_id: int,
        message: str,
    ) -> int:
        """Add a new message from any user to a group chat and return the message ID."""
        return self.add_user_to_group_chat(user_id, group_id, message)

    def add_private_message(
        self,
        sender_id: int,
        receiver_id: int,
        message: str,
    ) -> bool:
        """Add a private message to the pv field of a user."""
        try:
            conn = self._get_connection(database="chat", autocommit=True)
            cursor = conn.cursor()
            # Create the message object
            message_obj = {
                "sender_id": sender_id,
                "receiver_id": receiver_id,
                "message": message,
                "timestamp": "NOW()",
            }

            # Convert to JSON string
            message_json = json.dumps(message_obj)

            # Update the receiver's pv field
            cursor.execute(
                "UPDATE users SET pv = COALESCE(pv, '[]'::jsonb) || %s::jsonb WHERE id = %s",
                (message_json, receiver_id),
            )

            # Also update the sender's pv field if needed
            cursor.execute(
                "UPDATE users SET pv = COALESCE(pv, '[]'::jsonb) || %s::jsonb WHERE id = %s",
                (message_json, sender_id),
            )

            return True
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def remove_user(self, user_id: int) -> bool:
        """Remove a user from the users table."""
        try:
            conn = self._get_connection(database="chat", autocommit=True)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            return cursor.rowcount > 0
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e

    def remove_group(self, group_id: int) -> bool:
        """Remove a group from the groups table."""
        try:
            conn = self._get_connection(database="chat", autocommit=True)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM groups WHERE id = %s", (group_id,))
            return cursor.rowcount > 0
        except OperationalError as e:
            logger.debug(msg=str(e))
            raise e
