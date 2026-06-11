"""SQLite Session 示例实现。

中文学习说明：
- 这个文件演示如何把 Session 协议落到一个真实存储里：SQLite 表保存 session 和 message。
- 它不是唯一推荐方案，生产项目可以换成 Postgres/MySQL/Redis/对象存储，只要实现
  `get_items/add_items/pop_item/clear_session` 即可。
- 对 PPT Agent 来说，这可以作为本地开发期的项目对话历史存储参考；正式上线时建议后端
  数据库保存项目、任务、消息、生成文件索引。
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar

from ..items import TResponseInputItem
from .session import SessionABC
from .session_settings import SessionSettings, resolve_session_limit


class SQLiteSession(SessionABC):
    """SQLite-based implementation of session storage.

    This implementation stores conversation history in a SQLite database.
    By default, uses an in-memory database that is lost when the process ends.
    For persistent storage, provide a file path.
    """
    # SQLiteSession 适合作为轻量本地持久化。注意它保存的是 Responses input items，
    # 不是业务表结构；业务系统通常还需要自己的 projects/tasks/files 表。

    session_settings: SessionSettings | None = None
    _file_locks: ClassVar[dict[Path, threading.RLock]] = {}
    # ClassVar 表示类级别共享变量，不是实例字段。这里用来让同一进程内多个
    # SQLiteSession 共享同一个文件锁，避免并发写 SQLite 出问题。
    _file_lock_counts: ClassVar[dict[Path, int]] = {}
    _file_locks_guard: ClassVar[threading.Lock] = threading.Lock()

    def __init__(
        self,
        session_id: str,
        db_path: str | Path = ":memory:",
        sessions_table: str = "agent_sessions",
        messages_table: str = "agent_messages",
        session_settings: SessionSettings | None = None,
    ):
        """Initialize the SQLite session.

        Args:
            session_id: Unique identifier for the conversation session
            db_path: Path to the SQLite database file. Defaults to ':memory:' (in-memory database)
            sessions_table: Name of the table to store session metadata. Defaults to
                'agent_sessions'
            messages_table: Name of the table to store message data. Defaults to 'agent_messages'
            session_settings: Session configuration settings including default limit for
                retrieving items. If None, uses default SessionSettings().
        """
        self.session_id = session_id
        self.session_settings = session_settings or SessionSettings()
        self.db_path = db_path
        self.sessions_table = sessions_table
        self.messages_table = messages_table
        self._local = threading.local()
        # threading.local() 是线程本地存储：每个线程看到自己的 connection。
        self._connections: set[sqlite3.Connection] = set()
        self._connections_lock = threading.Lock()
        self._closed = False

        # For in-memory databases, we need a shared connection to avoid thread isolation
        # For file databases, we use thread-local connections for better concurrency
        # SQLite 的内存库跟连接绑定，所以必须共享连接；文件库则可以每线程一个连接。
        self._is_memory_db = str(db_path) == ":memory:"
        self._lock_path: Path | None = None
        self._lock_released = False
        if self._is_memory_db:
            self._lock = threading.RLock()
        else:
            self._lock_path, self._lock = self._acquire_file_lock(Path(self.db_path))

        try:
            if self._is_memory_db:
                self._shared_connection = sqlite3.connect(":memory:", check_same_thread=False)
                self._shared_connection.execute("PRAGMA journal_mode=WAL")
                self._init_db_for_connection(self._shared_connection)
            else:
                # For file databases, initialize the schema once since it persists
                with self._lock:
                    init_conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
                    init_conn.execute("PRAGMA journal_mode=WAL")
                    self._init_db_for_connection(init_conn)
                    init_conn.close()
        except Exception:
            if self._lock_path is not None and not self._lock_released:
                self._release_file_lock(self._lock_path)
                self._lock_released = True
            raise

    @classmethod
    def _acquire_file_lock(cls, db_path: Path) -> tuple[Path, threading.RLock]:
        """Return the path key and process-local lock for sessions sharing one SQLite file."""
        lock_path = db_path.expanduser().resolve()
        with cls._file_locks_guard:
            lock = cls._file_locks.get(lock_path)
            if lock is None:
                lock = threading.RLock()
                cls._file_locks[lock_path] = lock
                cls._file_lock_counts[lock_path] = 0
            cls._file_lock_counts[lock_path] += 1
            return lock_path, lock

    @classmethod
    def _release_file_lock(cls, lock_path: Path) -> None:
        """Drop the shared lock for a file-backed DB once the last session closes."""
        with cls._file_locks_guard:
            ref_count = cls._file_lock_counts.get(lock_path)
            if ref_count is None:
                return
            if ref_count <= 1:
                cls._file_lock_counts.pop(lock_path, None)
                cls._file_locks.pop(lock_path, None)
            else:
                cls._file_lock_counts[lock_path] = ref_count - 1

    @contextmanager
    def _locked_connection(self) -> Iterator[sqlite3.Connection]:
        """Serialize sqlite3 access while each operation runs in a worker thread."""
        # @contextmanager 让普通 generator 函数可以用于 `with`。
        # 这里保证一次数据库操作期间持有锁，结束后自动退出。
        with self._lock:
            yield self._get_connection()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        if self._closed:
            raise RuntimeError("SQLiteSession is closed")

        if self._is_memory_db:
            # Use shared connection for in-memory database to avoid thread isolation
            return self._shared_connection
        else:
            # Use thread-local connections for file databases
            if not hasattr(self._local, "connection"):
                connection = sqlite3.connect(
                    str(self.db_path),
                    check_same_thread=False,
                )
                connection.execute("PRAGMA journal_mode=WAL")
                self._local.connection = connection
                with self._connections_lock:
                    self._connections.add(connection)
            assert isinstance(self._local.connection, sqlite3.Connection), (
                f"Expected sqlite3.Connection, got {type(self._local.connection)}"
            )
            return self._local.connection

    def _init_db_for_connection(self, conn: sqlite3.Connection) -> None:
        """Initialize the database schema for a specific connection."""
        # 注意这里直接拼表名，所以表名应来自受信任配置，不要把用户输入拼进 SQL 标识符。
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.sessions_table} (
                session_id TEXT PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.messages_table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES {self.sessions_table} (session_id)
                    ON DELETE CASCADE
            )
        """
        )

        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self.messages_table}_session_id
            ON {self.messages_table} (session_id, id)
        """
        )

        conn.commit()

    def _insert_items(self, conn: sqlite3.Connection, items: list[TResponseInputItem]) -> None:
        # 先确保 session 元数据存在，再批量插入 message JSON。
        conn.execute(
            f"""
            INSERT OR IGNORE INTO {self.sessions_table} (session_id) VALUES (?)
        """,
            (self.session_id,),
        )

        message_data = [(self.session_id, json.dumps(item)) for item in items]
        conn.executemany(
            f"""
            INSERT INTO {self.messages_table} (session_id, message_data) VALUES (?, ?)
        """,
            message_data,
        )

        conn.execute(
            f"""
            UPDATE {self.sessions_table}
            SET updated_at = CURRENT_TIMESTAMP
            WHERE session_id = ?
        """,
            (self.session_id,),
        )

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        """Retrieve the conversation history for this session.

        Args:
            limit: Maximum number of items to retrieve. If None, uses session_settings.limit.
                   When specified, returns the latest N items in chronological order.

        Returns:
            List of input items representing the conversation history
        """
        session_limit = resolve_session_limit(limit, self.session_settings)

        def _get_items_sync():
            # sqlite3 是同步库。外层用 asyncio.to_thread 把阻塞操作放到线程池，
            # 避免阻塞事件循环。
            with self._locked_connection() as conn:
                if session_limit is None:
                    # Fetch all items in chronological order
                    cursor = conn.execute(
                        f"""
                        SELECT message_data FROM {self.messages_table}
                        WHERE session_id = ?
                        ORDER BY id ASC
                    """,
                        (self.session_id,),
                    )
                else:
                    # Fetch the latest N items in chronological order
                    cursor = conn.execute(
                        f"""
                        SELECT message_data FROM {self.messages_table}
                        WHERE session_id = ?
                        ORDER BY id DESC
                        LIMIT ?
                        """,
                        (self.session_id, session_limit),
                    )

                rows = cursor.fetchall()

                # Reverse to get chronological order when using DESC
                if session_limit is not None:
                    rows = list(reversed(rows))

                items = []
                for (message_data,) in rows:
                    try:
                        item = json.loads(message_data)
                        items.append(item)
                    except (json.JSONDecodeError, TypeError):
                        # Skip invalid JSON entries
                        continue

                return items

        return await asyncio.to_thread(_get_items_sync)

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        """Add new items to the conversation history.

        Args:
            items: List of input items to add to the history
        """
        if not items:
            return

        def _add_items_sync():
            # 批量写入要和 commit 放在同一个锁保护区内。
            with self._locked_connection() as conn:
                self._insert_items(conn, items)
                conn.commit()

        await asyncio.to_thread(_add_items_sync)

    async def pop_item(self) -> TResponseInputItem | None:
        """Remove and return the most recent item from the session.

        Returns:
            The most recent item if it exists, None if the session is empty
        """

        def _pop_item_sync():
            with self._locked_connection() as conn:
                # Use DELETE with RETURNING to atomically delete and return the most recent item
                # DELETE ... RETURNING 可以原子地“删除并返回最后一条”，适合重试回滚。
                cursor = conn.execute(
                    f"""
                    DELETE FROM {self.messages_table}
                    WHERE id = (
                        SELECT id FROM {self.messages_table}
                        WHERE session_id = ?
                        ORDER BY id DESC
                        LIMIT 1
                    )
                    RETURNING message_data
                    """,
                    (self.session_id,),
                )

                result = cursor.fetchone()
                conn.commit()

                while result:
                    message_data = result[0]
                    try:
                        item = json.loads(message_data)
                        return item
                    except (json.JSONDecodeError, TypeError):
                        # Drop corrupted JSON entries and keep looking for a valid item.
                        cursor = conn.execute(
                            f"""
                            DELETE FROM {self.messages_table}
                            WHERE id = (
                                SELECT id FROM {self.messages_table}
                                WHERE session_id = ?
                                ORDER BY id DESC
                                LIMIT 1
                            )
                            RETURNING message_data
                            """,
                            (self.session_id,),
                        )
                        result = cursor.fetchone()
                        conn.commit()

                return None

        return await asyncio.to_thread(_pop_item_sync)

    async def clear_session(self) -> None:
        """Clear all items for this session."""

        def _clear_session_sync():
            with self._locked_connection() as conn:
                conn.execute(
                    f"DELETE FROM {self.messages_table} WHERE session_id = ?",
                    (self.session_id,),
                )
                conn.execute(
                    f"DELETE FROM {self.sessions_table} WHERE session_id = ?",
                    (self.session_id,),
                )
                conn.commit()

        await asyncio.to_thread(_clear_session_sync)

    def close(self) -> None:
        """Close the database connection."""
        # 服务退出或测试结束时应关闭连接并释放文件锁。
        with self._lock:
            if self._closed:
                return

            self._closed = True
            if self._is_memory_db:
                if hasattr(self, "_shared_connection"):
                    self._shared_connection.close()
            else:
                with self._connections_lock:
                    connections = list(self._connections)
                    self._connections.clear()
                for connection in connections:
                    connection.close()
            if self._lock_path is not None and not self._lock_released:
                self._release_file_lock(self._lock_path)
                self._lock_released = True
