#db_mcp_server.py
import os
import asyncio
import contextlib
from typing import Dict, Any
import requests
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from fastmcp import FastMCP
from logger_utils import get_logger

#環境変数の読み込み
load_dotenv()

logger = get_logger(__name__)

# 環境変数からDB設定値を取得
class DBSettings(BaseSettings):
    host: str  = Field(default=os.getenv("MYSQL_HOST", "mysql"))
    port: int  = Field(default=int(os.getenv("MYSQL_PORT", "3306")))
    root_user: str = Field(default=os.getenv("MYSQL_ROOT_USER", "root"))
    root_password: str = Field(default=os.getenv("MYSQL_ROOT_PASSWORD", "root_pass_change_me"))
    database: str = Field(default=os.getenv("MYSQL_DATABASE", "classicmodels"))
    app_user: str  = Field(default=os.getenv("APP_USER", "app_user"))
    app_password: str = Field(default=os.getenv("APP_PASSWORD", "app_pass_change_me"))
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = DBSettings()

# DB接続用のヘルパー関数
def get_root_connection() -> mysql.connector.MySQLConnection:
    """rootユーザーでDB接続"""
    conn = mysql.connector.connect(
        host=settings.host,
        port=settings.port,
        user=settings.root_user,
        password=settings.root_password,
    )
    conn.autocommit = True
    return conn

def get_app_connection(*, use_pure: bool = False) -> mysql.connector.MySQLConnection:
    """アプリケーションユーザーでDB接続"""
    return mysql.connector.connect(
        host=settings.host,
        port=settings.port,
        user=settings.app_user,
        password=settings.app_password,
        database=settings.database,
        use_pure=use_pure,
    )

def get_connection() -> mysql.connector.MySQLConnection:
    """MCPツールでDB接続"""
    return mysql.connector.connect(
        host=settings.host,
        port=settings.port,
        user=settings.app_user,
        password=settings.app_password,
        database=settings.database or None,
    )

# サンプルSQLのURL
CLASSICMODELS_SQL_URL = (
    "https://gist.githubusercontent.com/prof3ssorSt3v3/"
    "796ebc82fd8eeb0b697effaa1e86c3a6/raw/classicmodels.sql"
)

def _setup_database_and_user() -> None:
    """DB作成・ユーザー作成"""
    with contextlib.closing(get_root_connection()) as conn, conn.cursor() as cur:
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{settings.database}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
        )
        cur.execute(
            "CREATE USER IF NOT EXISTS %s@'%%' IDENTIFIED BY %s;",
            (settings.app_user, settings.app_password),
        )
        cur.execute(
            f"GRANT ALL PRIVILEGES ON `{settings.database}`.* TO %s@'%%';",
            (settings.app_user,),
        )
        cur.execute("FLUSH PRIVILEGES;")
    logger.info("Database and user setup complete.")

def _download_classicmodels_sql() -> str:
    """サンプルSQLのダウンロード"""
    resp = requests.get(CLASSICMODELS_SQL_URL, timeout=30)
    resp.raise_for_status()
    return resp.text

def _import_sql(sql_script: str) -> None:
    """サンプルSQLをDBにインポート"""
    with contextlib.closing(get_app_connection(use_pure=True)) as conn, conn.cursor() as cur:
        for _ in cur.execute(sql_script, multi=True):
            pass
        conn.commit()

def prepare_classicmodels() -> str:
    """DBを構築するメインユーティリティ"""
    try:
        _setup_database_and_user()
        sql_script = _download_classicmodels_sql()
        _import_sql(sql_script)
        return "classicmodels import completed."
    except Exception as exc:
        logger.exception("classicmodels import failed") 
        return f" Failed: {exc}"

#MCPサーバのインスタンス化
mcp = FastMCP("DB MCP Server")

_initialization_lock = asyncio.Lock()
_is_initialized = False

async def initialize_resources() -> None:
    """DBの初期化"""
    global _is_initialized
    async with _initialization_lock:
        if _is_initialized:
            return
        logger.info("Initializing server resources...")
        logger.info(prepare_classicmodels())
        _is_initialized = True
        logger.info("All server resources initialized successfully")

# MCP toolの定義
@mcp.tool(
    name="mysql_query_select",
    description="MySQLでSELECTクエリを実行し結果を返します",
    tags={"database", "mysql", "query", "select", "search"},
)
def mysql_query_select(query: str) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query)
        rows = cursor.fetchall()
        return {
            "rows": rows[:100],
            "row_count": cursor.rowcount,
            "column_names": [d[0] for d in cursor.description] if cursor.description else []
        }
    except Error as e:
        raise Exception(f"Query error: {e}") from e
    finally:
        cursor.close()
        conn.close()

@mcp.tool(
    name="mysql_execute_dml",
    description="INSERT / UPDATE / DELETE を実行し影響行数を返します。",
    tags={"database", "mysql", "execute", "dml", "write"},
)
def mysql_execute_dml(query: str) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(query)
        conn.commit()
        return {"affected_rows": cursor.rowcount, "last_insert_id": cursor.lastrowid or None}
    except Error as e:
        conn.rollback()
        raise Exception(f"Execute error: {e}") from e
    finally:
        cursor.close()
        conn.close()

@mcp.tool(
    name="mysql_list_databases",
    description="データベース(DB)の一覧を取得します",
    tags={"database", "mysql", "metadata", "list", "info"},
)
def mysql_list_databases() -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SHOW DATABASES")
        return {"databases": [db[0] for db in cursor.fetchall()]}
    finally:
        cursor.close()
        conn.close()

@mcp.tool(
    name="mysql_switch_database",
    description="対象のデータベース(DB)に切り替えます",
    tags={"database", "mysql", "switch", "config"},
)
def mysql_switch_database(database: str) -> Dict[str, Any]:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SHOW DATABASES")
        available = [d[0] for d in cursor.fetchall()]
        if database not in available:
            raise ValueError(f"Database '{database}' does not exist")
        settings.database = database
        return {"current_database": database, "status": "success"}
    finally:
        cursor.close()
        conn.close()

@mcp.tool(
    name="mysql_list_tables",
    description="対象データベース（DB）内のテーブル一覧を取得します",
    tags={"database", "mysql", "metadata", "list", "tables","show"},
)
def mysql_list_tables() -> Dict[str, Any]:
    if not settings.database:
        raise ValueError("No database selected. Use 'mysql_switch_database' first.")
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SHOW TABLES")
        return {"database": settings.database, "tables": [t[0] for t in cursor.fetchall()]}
    finally:
        cursor.close()
        conn.close()

@mcp.tool(
    name="mysql_describe_table",
    description="対象テーブルのカラム仕様とインデックス情報を取得します",
    tags={"database", "mysql", "metadata", "schema", "table", "describe","structure", "definition", "columns", "indexes"},
)
def mysql_describe_table(table: str) -> Dict[str, Any]:
    if not settings.database:
        raise ValueError("No database selected. Use 'mysql_switch_database' first.")
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(f"DESCRIBE {table}")
        columns = cursor.fetchall()
        cursor.execute(f"SHOW INDEX FROM {table}")
        indexes = cursor.fetchall()
        return {"table": table, "columns": columns, "indexes": indexes}
    finally:
        cursor.close()
        conn.close()

@mcp.tool(name="server_status")
async def server_status() -> str:
    """サーバー初期化状態を返す簡易ヘルスチェック"""
    return f" Server Status: initialized={_is_initialized}"

# エントリポイント
if __name__ == "__main__":
    async def main() -> None:
        logger.info("DB MCP server starting...")
        await initialize_resources()
        await mcp.run_async(
            transport="streamable-http",
            host="0.0.0.0",
            port=3000,
            path="/mcp",
            log_level="info",
        )
    asyncio.run(main())