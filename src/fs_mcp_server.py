#fs_mcp_server.py
import json
import mimetypes
import os
import platform
import shutil
import subprocess
import tempfile
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from fastmcp import FastMCP
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from logger_utils import get_logger

# .envファイルから環境変数を読み込む
load_dotenv()

logger = get_logger(__name__)

# 実行中のオペレーティングシステム
SYSTEM = platform.system()

# プロジェクトのルートディレクトリを取得
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# .envファイルからDEFAULT_FS_PATHを取得
DEFAULT_FS_PATH = os.getenv('DEFAULT_FS_PATH', os.path.join(PROJECT_ROOT, "data"))

# プロジェクト内で使用する基準ディレクトリを設定
DEFAULT_BASE_DIR = DEFAULT_FS_PATH

# 上記ディレクトリが存在しない場合は作成する
os.makedirs(DEFAULT_BASE_DIR, exist_ok=True)


# MIMEタイプの初期化
mimetypes.init()

# ファイルメタデータの構造を定義
class FileMetadata(BaseModel):
    path: str
    name: str
    size: int
    created: str
    modified: str
    type: str
    preview: Optional[str] = None
    line_count: Optional[int] = None
    preview_error: Optional[str] = None
    error: Optional[str] = None

class FileContent(BaseModel):
    path: str
    name: str
    content: str
    size: int
    error: Optional[str] = None

class FileWriteResult(BaseModel):
    success: bool
    path: str
    name: str
    size: int
    mode: str
    error: Optional[str] = None

class FileMatch(BaseModel):
    context: str
    line: int

class FileSearchResult(BaseModel):
    path: str
    name: str
    size: int
    created: str
    modified: str
    type: str
    match: Optional[FileMatch] = None
    error: Optional[str] = None

class DirectoryItem(BaseModel):
    name: str
    path: str

class FileItem(BaseModel):
    name: str
    path: str
    size: int
    type: str

class DirectoryListing(BaseModel):
    path: str
    files: List[FileItem]
    directories: List[DirectoryItem]
    file_count: int
    directory_count: int
    error: Optional[str] = None

class DriveInfo(BaseModel):
    path: str
    type: str

class DriveListing(BaseModel):
    drives: List[DriveInfo]
    error: Optional[str] = None

class CollectionResult(BaseModel):
    collection: str
    file_count: int
    path: str
    error: Optional[str] = None

class SystemInfo(BaseModel):
    system: str
    node: str
    release: str
    version: str
    machine: str
    processor: str
    python_version: str
    user_home: str
    environment_error: Optional[str] = None

class SystemInfoResult(BaseModel):
    system_info: SystemInfo
    error: Optional[str] = None

class FileCopyResult(BaseModel):
    success: bool
    source: str
    destination: str
    size: int
    error: Optional[str] = None

class FileMoveResult(BaseModel):
    success: bool
    source: str
    destination: str
    size: int
    error: Optional[str] = None

class FileDeleteInfo(BaseModel):
    path: str
    name: str
    size: int

class FileDeleteResult(BaseModel):
    success: bool
    deleted_file: FileDeleteInfo
    error: Optional[str] = None

class DirectoryCreateResult(BaseModel):
    success: bool
    path: str
    error: Optional[str] = None

class ScanDirectoryResult(BaseModel):
    directory: str
    file_count: int
    files: List[FileMetadata]
    error: Optional[str] = None

class SearchFilesResult(BaseModel):
    directory: str
    query: str
    match_count: int
    matches: List[FileMetadata]
    error: Optional[str] = None

class SearchFileContentsResult(BaseModel):
    directory: str
    query: str
    match_count: int
    matches: List[FileSearchResult]
    error: Optional[str] = None

class UserDirectoriesResult(BaseModel):
    directories: Dict[str, str]
    error: Optional[str] = None

class RecursiveDirectoryListing(BaseModel):
    path: str
    structure: str
    file_count: int
    directory_count: int
    error: Optional[str] = None

# ヘルパー関数
def get_file_type(file_path):
    """ファイルのMIMEタイプまたは拡張子に基づき分類（例: image, video, pdf など）を返す"""
    mime_type, _ = mimetypes.guess_type(file_path)
    
    if mime_type:
        if mime_type.startswith('image/'):
            return 'image'
        elif mime_type.startswith('video/'):
            return 'video'
        elif mime_type.startswith('audio/'):
            return 'audio'
        elif mime_type.startswith('text/'):
            return 'text'
        elif mime_type.startswith('application/pdf'):
            return 'pdf'
        elif mime_type.startswith('application/msword') or mime_type.startswith('application/vnd.openxmlformats-officedocument.wordprocessingml'):
            return 'document'
        elif mime_type.startswith('application/vnd.ms-excel') or mime_type.startswith('application/vnd.openxmlformats-officedocument.spreadsheetml'):
            return 'spreadsheet'
        elif mime_type.startswith('application/vnd.ms-powerpoint') or mime_type.startswith('application/vnd.openxmlformats-officedocument.presentationml'):
            return 'presentation'
    
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']:
        return 'image'
    elif ext in ['.mp4', '.avi', '.mov', '.wmv', '.mkv', '.flv', '.webm']:
        return 'video'
    elif ext in ['.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a']:
        return 'audio'
    elif ext in ['.pdf', '.txt', '.md', '.rtf']:
        return 'document'
    elif ext in ['.py', '.js', '.html', '.css', '.java', '.cpp', '.c', '.h', '.cs', '.php', '.rb', '.go', '.rs', '.ts']:
        return 'code'
    elif ext in ['.csv', '.json', '.xml', '.yaml', '.yml', '.sql', '.db', '.sqlite']:
        return 'data'
    elif ext in ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2']:
        return 'archive'
    elif ext in ['.exe', '.msi', '.bat', '.sh', '.app', '.dmg']:
        return 'executable'
    elif ext in ['.doc', '.docx']:
        return 'document'
    elif ext in ['.xls', '.xlsx']:
        return 'spreadsheet'
    elif ext in ['.ppt', '.pptx']:
        return 'presentation'
    
    return 'unknown'

def get_file_metadata(file_path):
    """ファイルサイズや作成日時などを取得する関数"""
    try:
        stat_info = os.stat(file_path)
        file_size = stat_info.st_size
        created_time = datetime.fromtimestamp(stat_info.st_ctime)
        modified_time = datetime.fromtimestamp(stat_info.st_mtime)
        
        file_type = get_file_type(file_path)
        
        metadata = {
            "path": file_path,
            "name": os.path.basename(file_path),
            "size": file_size,
            "created": created_time.isoformat(),
            "modified": modified_time.isoformat(),
            "type": file_type
        }
        
        if file_type in ['text', 'code', 'document'] and os.path.splitext(file_path)[1].lower() in ['.txt', '.md', '.csv', '.json', '.xml', '.html', '.css', '.js', '.py', '.java', '.c', '.cpp', '.h', '.cs', '.php', '.rb', '.go', '.rs', '.ts']:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    preview = f.read(1000)
                    if len(preview) == 1000:
                        preview += "... (truncated)"
                    metadata["preview"] = preview
                    
                    f.seek(0)
                    line_count = sum(1 for _ in f)
                    metadata["line_count"] = line_count
            except Exception as e:
                metadata["preview_error"] = str(e)
        
        return FileMetadata(**metadata)
    except Exception as e:
        return FileMetadata(
            path=file_path,
            name=os.path.basename(file_path),
            size=0,
            created=datetime.now().isoformat(),
            modified=datetime.now().isoformat(),
            type="unknown",
            error=str(e)
        )

def scan_directory(directory_path, recursive=True, file_types=None):
    """指定フォルダをスキャンする"""
    results = []
    try:
        if recursive:
            for root, _, files in os.walk(directory_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    file_type = get_file_type(file_path)
                    if file_types is None or file_type in file_types:
                        results.append(get_file_metadata(file_path))
        else:
            for item in os.listdir(directory_path):
                item_path = os.path.join(directory_path, item)
                if os.path.isfile(item_path):
                    file_type = get_file_type(item_path)
                    if file_types is None or file_type in file_types:
                        results.append(get_file_metadata(item_path))
    except Exception as e:
        return {"error": str(e)}
    return results

def read_text_file(file_path, max_lines=None):
    """テキストファイルを読み込む"""
    try:
        if not os.path.isfile(file_path):
            return FileContent(path=file_path, name=os.path.basename(file_path), content="", size=0, error=f"File not found: {file_path}")
        
        file_type = get_file_type(file_path)
        if file_type not in ['text', 'code', 'document']:
            return FileContent(path=file_path, name=os.path.basename(file_path), content="", size=os.path.getsize(file_path), error=f"Not a text file: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            if max_lines:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    lines.append(line)
                content = ''.join(lines)
                if i >= max_lines:
                    content += f"\n... (truncated, showing {max_lines} of {i+1}+ lines)"
            else:
                content = f.read()
        
        return FileContent(path=file_path, name=os.path.basename(file_path), content=content, size=os.path.getsize(file_path))
    except Exception as e:
        return FileContent(path=file_path, name=os.path.basename(file_path), content="", size=0, error=str(e))

def write_text_file(file_path, content, append=False):
    """テキストファイルに書き込む"""
    try:
        mode = 'a' if append else 'w'
        with open(file_path, mode, encoding='utf-8') as f:
            f.write(content)
        return FileWriteResult(success=True, path=file_path, name=os.path.basename(file_path), size=os.path.getsize(file_path), mode="append" if append else "write")
    except Exception as e:
        return FileWriteResult(success=False, path=file_path, name=os.path.basename(file_path), size=0, mode="append" if append else "write", error=str(e))

def search_files(directory_path, query, recursive=True, file_types=None):
    """ファイル名の検索"""
    results = []
    try:
        query = query.lower()
        if recursive:
            for root, _, files in os.walk(directory_path):
                for file in files:
                    if query in file.lower():
                        file_path = os.path.join(root, file)
                        file_type = get_file_type(file_path)
                        if file_types is None or file_type in file_types:
                            results.append(get_file_metadata(file_path))
        else:
            for item in os.listdir(directory_path):
                if query in item.lower() and os.path.isfile(os.path.join(directory_path, item)):
                    file_path = os.path.join(directory_path, item)
                    file_type = get_file_type(file_path)
                    if file_types is None or file_type in file_types:
                        results.append(get_file_metadata(file_path))
    except Exception as e:
        return {"error": str(e)}
    return results

def search_file_contents(directory_path, query, recursive=True, file_types=None, max_results=100):
    """ファイルの内容から検索"""
    results = []
    count = 0
    try:
        query = query.lower()
        searchable_types = ['text', 'code', 'document']
        searchable_extensions = ['.txt', '.md', '.csv', '.json', '.xml', '.html', '.css', '.js', '.py', '.java', '.c', '.cpp', '.h', '.cs', '.php', '.rb', '.go', '.rs', '.ts']
        
        def check_and_append(path):
            nonlocal count
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                if query in content.lower():
                    metadata = get_file_metadata(path)
                    index = content.lower().find(query)
                    start = max(0, index - 50)
                    end = min(len(content), index + len(query) + 50)
                    line_number = content[:index].count('\n') + 1
                    results.append(FileSearchResult(**metadata.dict(), match=FileMatch(context=content[start:end], line=line_number)))
                    count += 1
            except Exception:
                pass
        
        if recursive:
            for root, _, files in os.walk(directory_path):
                for file in files:
                    if count >= max_results:
                        break
                    path = os.path.join(root, file)
                    ext = os.path.splitext(path)[1].lower()
                    if (file_types is None or get_file_type(path) in file_types) and (get_file_type(path) in searchable_types or ext in searchable_extensions):
                        check_and_append(path)
        else:
            for item in os.listdir(directory_path):
                if count >= max_results:
                    break
                path = os.path.join(directory_path, item)
                if os.path.isfile(path):
                    ext = os.path.splitext(path)[1].lower()
                    if (file_types is None or get_file_type(path) in file_types) and (get_file_type(path) in searchable_types or ext in searchable_extensions):
                        check_and_append(path)
    except Exception as e:
        return {"error": str(e)}
    return results

#　MCPサーバのインスタンス化
mcp = FastMCP("FS MCP Server")

# MCP Toolの定義
@mcp.tool(
    name="scan_directory",
    description="ディレクトリ内のファイルをスキャンしてメタデータを取得します。",
    tags=["filesystem", "scan", "metadata"]
)
def scan_directory_tool(directory_path: str, recursive: bool = True, file_types: list = None) -> Dict[str, Any]:
    if not os.path.isdir(directory_path):
        return ScanDirectoryResult(
            directory=directory_path,
            file_count=0,
            files=[],
            error=f"Directory not found: {directory_path}"
        ).model_dump()

    results = scan_directory(directory_path, recursive, file_types)

    if isinstance(results, dict) and "error" in results:
        return ScanDirectoryResult(
            directory=directory_path,
            file_count=0,
            files=[],
            error=results["error"]
        ).model_dump()

    return ScanDirectoryResult(
        directory=directory_path,
        file_count=len(results),
        files=results
    ).model_dump()

@mcp.tool(
    name="get_file_metadata",
    description="ファイルのパスからメタデータ（サイズ、作成日時など）を取得します",
    tags=["filesystem", "metadata", "file"]
)
def get_file_metadata_tool(file_path: str) -> Dict[str, Any]:
    if not os.path.isfile(file_path):
        return FileMetadata(
            path=file_path,
            name=os.path.basename(file_path),
            size=0,
            created=datetime.now().isoformat(),
            modified=datetime.now().isoformat(),
            type="unknown",
            error=f"File not found: {file_path}"
        ).model_dump()

    # Get the file metadata
    metadata = get_file_metadata(file_path)
    return metadata.model_dump()

@mcp.tool(
    name="list_user_directories",
    description="ユーザーの共通ディレクトリ（Desktop, Documents など）を一覧表示します",
    tags=["filesystem", "user", "directories"]
)
def list_user_directories() -> Dict[str, Any]:
    directories = {}

    try:
        if SYSTEM == "Darwin":  # macOS
            for dir_name, folder in [
                ("Desktop", "Desktop"),
                ("Documents", "Documents"),
                ("Pictures", "Pictures"),
                ("Movies", "Movies"),
                ("Music", "Music"),
                ("Downloads", "Downloads"),
                ("Applications", "Applications"),
                ("Library", "Library")
            ]:
                path = os.path.join(os.path.expanduser("~"), folder)
                if os.path.isdir(path):
                    directories[dir_name] = path

        else:  # Linux and other UNIX-like systems
            try:
                import subprocess
                for dir_name, xdg_key in [
                    ("Desktop", "DESKTOP"),
                    ("Documents", "DOCUMENTS"),
                    ("Pictures", "PICTURES"),
                    ("Videos", "VIDEOS"),
                    ("Music", "MUSIC"),
                    ("Downloads", "DOWNLOAD"),
                    ("Templates", "TEMPLATES"),
                    ("Public", "PUBLICSHARE")
                ]:
                    try:
                        path = subprocess.check_output(
                            ["xdg-user-dir", xdg_key],
                            universal_newlines=True
                        ).strip()
                        if os.path.isdir(path):
                            directories[dir_name] = path
                    except:
                        path = os.path.join(os.path.expanduser("~"), dir_name)
                        if os.path.isdir(path):
                            directories[dir_name] = path
            except:
                for dir_name in ["Desktop", "Documents", "Pictures", "Videos", "Music", "Downloads"]:
                    path = os.path.join(os.path.expanduser("~"), dir_name)
                    if os.path.isdir(path):
                        directories[dir_name] = path

        return UserDirectoriesResult(directories=directories).model_dump()
    except Exception as e:
        return UserDirectoriesResult(
            directories={},
            error=str(e)
        ).model_dump()

@mcp.tool(
    name="read_file",
    description="ファイルの内容を読み込んで表示します",
    tags=["filesystem", "file", "read"]
)
def read_text_file_tool(file_path: str, max_lines: int = None) -> Dict[str, Any]:
    return read_text_file(file_path, max_lines).model_dump()


# MCP Tool: Write Text File
@mcp.tool(
    name="create_text_file",
    description="テキストファイルに内容を書き込み保存します。",
    tags=["filesystem", "file", "write"]
)
def write_text_file_tool(file_path: str, content: str, append: bool = False) -> Dict[str, Any]:
    """
    Write content to a text file.

    Args:
        file_path: The path to the text file
        content: The content to write
        append: Whether to append to the file (True) or overwrite it (False)

    Returns:
        Information about the written file
    """
    return write_text_file(file_path, content, append).model_dump()

@mcp.tool(
    name="search_files",
    description="ファイル名にマッチするファイルを指定ディレクトリで検索します",
    tags=["filesystem", "search", "file"]
)
def search_files_tool(directory_path: str, query: str, recursive: bool = True, file_types: list = None) -> Dict[str, Any]:
    if not os.path.isdir(directory_path):
        return SearchFilesResult(
            directory=directory_path,
            query=query,
            match_count=0,
            matches=[],
            error=f"Directory not found: {directory_path}"
        ).model_dump()

    results = search_files(directory_path, query, recursive, file_types)

    if isinstance(results, dict) and "error" in results:
        return SearchFilesResult(
            directory=directory_path,
            query=query,
            match_count=0,
            matches=[],
            error=results["error"]
        ).model_dump()

    return SearchFilesResult(
        directory=directory_path,
        query=query,
        match_count=len(results),
        matches=results
    ).model_dump()

@mcp.tool(
    name="search_file_contents",
    description="ファイル内容にクエリが含まれるファイルを検索し、コンテキスト付きで返します",
    tags=["filesystem", "search", "content"]
)
def search_file_contents_tool(directory_path: str, query: str, recursive: bool = True, file_types: list = None, max_results: int = 100) -> Dict[str, Any]:
    if not os.path.isdir(directory_path):
        return SearchFileContentsResult(
            directory=directory_path,
            query=query,
            match_count=0,
            matches=[],
            error=f"Directory not found: {directory_path}"
        ).model_dump()

    results = search_file_contents(directory_path, query, recursive, file_types, max_results)

    if isinstance(results, dict) and "error" in results:
        return SearchFileContentsResult(
            directory=directory_path,
            query=query,
            match_count=0,
            matches=[],
            error=results["error"]
        ).model_dump()

    return SearchFileContentsResult(
        directory=directory_path,
        query=query,
        match_count=len(results),
        matches=results
    ).model_dump()

@mcp.tool(
    name="get_system_info",
    description="システムの基本情報（OS、ホスト名、Pythonバージョンなど）を取得します",
    tags=["system", "info", "environment"]
)
def get_system_info() -> Dict[str, Any]:
    try:
        info = {
            "system": platform.system(),
            "node": platform.node(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "user_home": os.path.expanduser("~")
        }
        return SystemInfoResult(system_info=SystemInfo(**info)).model_dump()
    except Exception as e:
        return SystemInfoResult(
            system_info=SystemInfo(
                system=platform.system(),
                node="unknown",
                release="unknown",
                version="unknown",
                machine="unknown",
                processor="unknown",
                python_version=platform.python_version(),
                user_home=os.path.expanduser("~")
            ),
            error=str(e)
        ).model_dump()

@mcp.tool(
    name="copy_file",
    description="ファイルを指定先にコピーします",
    tags=["filesystem", "file", "copy"]
)
def copy_file(source_path: str, destination_path: str, overwrite: bool = False) -> Dict[str, Any]:
    try:
        if not os.path.isfile(source_path):
            return FileCopyResult(
                success=False,
                source=source_path,
                destination=destination_path,
                size=0,
                error=f"Source file not found: {source_path}"
            ).model_dump()

        if os.path.exists(destination_path) and not overwrite:
            return FileCopyResult(
                success=False,
                source=source_path,
                destination=destination_path,
                size=0,
                error=f"Destination file already exists: {destination_path}"
            ).model_dump()

        os.makedirs(os.path.dirname(os.path.abspath(destination_path)), exist_ok=True)
        shutil.copy2(source_path, destination_path)

        return FileCopyResult(
            success=True,
            source=source_path,
            destination=destination_path,
            size=os.path.getsize(destination_path)
        ).model_dump()
    except Exception as e:
        return FileCopyResult(
            success=False,
            source=source_path,
            destination=destination_path,
            size=0,
            error=str(e)
        ).model_dump()

@mcp.tool(
    name="move_file",
    description="ファイルを指定先に移動します。",
    tags=["filesystem", "file", "move"]
)
def move_file(source_path: str, destination_path: str, overwrite: bool = False) -> Dict[str, Any]:
    try:
        if not os.path.isfile(source_path):
            return FileMoveResult(
                success=False,
                source=source_path,
                destination=destination_path,
                size=0,
                error=f"Source file not found: {source_path}"
            ).model_dump()

        if os.path.exists(destination_path) and not overwrite:
            return FileMoveResult(
                success=False,
                source=source_path,
                destination=destination_path,
                size=0,
                error=f"Destination file already exists: {destination_path}"
            ).model_dump()

        os.makedirs(os.path.dirname(os.path.abspath(destination_path)), exist_ok=True)
        file_size = os.path.getsize(source_path)
        shutil.move(source_path, destination_path)

        return FileMoveResult(
            success=True,
            source=source_path,
            destination=destination_path,
            size=file_size
        ).model_dump()
    except Exception as e:
        return FileMoveResult(
            success=False,
            source=source_path,
            destination=destination_path,
            size=0,
            error=str(e)
        ).model_dump()

@mcp.tool(
    name="delete_file",
    description="指定したファイルを削除します。",
    tags=["filesystem", "file", "delete"]
)
def delete_file(file_path: str) -> Dict[str, Any]:
    try:
        if not os.path.isfile(file_path):
            return FileDeleteResult(
                success=False,
                deleted_file=FileDeleteInfo(
                    path=file_path,
                    name=os.path.basename(file_path),
                    size=0
                ),
                error=f"File not found: {file_path}"
            ).model_dump()

        file_info = FileDeleteInfo(
            path=file_path,
            name=os.path.basename(file_path),
            size=os.path.getsize(file_path)
        )
        os.remove(file_path)

        return FileDeleteResult(
            success=True,
            deleted_file=file_info
        ).model_dump()
    except Exception as e:
        return FileDeleteResult(
            success=False,
            deleted_file=FileDeleteInfo(
                path=file_path,
                name=os.path.basename(file_path),
                size=0
            ),
            error=str(e)
        ).model_dump()

@mcp.tool(
    name="create_directory",
    description="新しいディレクトリを作成します",
    tags=["filesystem", "directory", "create"]
)
def create_directory(directory_path: str) -> Dict[str, Any]:
    try:
        os.makedirs(directory_path, exist_ok=True)
        return DirectoryCreateResult(
            success=True,
            path=directory_path
        ).model_dump()
    except Exception as e:
        return DirectoryCreateResult(
            success=False,
            path=directory_path,
            error=str(e)
        ).model_dump()

@mcp.tool(
    name="list_directory",
    description="ディレクトリ内のファイルとサブディレクトリを一覧表示します。",
    tags=["filesystem", "directory", "list", "file"]
)
def list_directory(directory_path: str) -> Dict[str, Any]:
    try:
        if not os.path.isdir(directory_path):
            return DirectoryListing(
                path=directory_path,
                files=[],
                directories=[],
                file_count=0,
                directory_count=0,
                error=f"Directory not found: {directory_path}"
            ).model_dump()

        items = os.listdir(directory_path)
        files = []
        directories = []

        for item in items:
            item_path = os.path.join(directory_path, item)
            if os.path.isfile(item_path):
                files.append(FileItem(
                    name=item,
                    path=item_path,
                    size=os.path.getsize(item_path),
                    type=get_file_type(item_path)
                ))
            elif os.path.isdir(item_path):
                directories.append(DirectoryItem(
                    name=item,
                    path=item_path
                ))

        return DirectoryListing(
            path=directory_path,
            files=files,
            directories=directories,
            file_count=len(files),
            directory_count=len(directories)
        ).model_dump()
    except Exception as e:
        return DirectoryListing(
            path=directory_path,
            files=[],
            directories=[],
            file_count=0,
            directory_count=0,
            error=str(e)
        ).model_dump()

@mcp.tool(
    name="list_directory_recursively",
    description="ディレクトリ構造を再帰的に表示し、深さを制限します。",
    tags=["filesystem", "directory", "recursive"]
)
def list_directory_recursively(directory_path: str, max_depth: int = 3) -> Dict[str, Any]:
    try:
        if not os.path.isdir(directory_path):
            return RecursiveDirectoryListing(
                path=directory_path,
                structure="",
                file_count=0,
                directory_count=0,
                error=f"Directory not found: {directory_path}"
            ).model_dump()

        def build_tree(path: str, prefix: str = "", depth: int = 0) -> tuple[str, int, int]:
            if depth >= max_depth:
                return "", 0, 0

            tree = []
            file_count = 0
            dir_count = 0

            try:
                items = os.listdir(path)
                items.sort(key=lambda x: (not os.path.isdir(os.path.join(path, x)), x.lower()))

                for i, item in enumerate(items):
                    is_last = i == len(items) - 1
                    item_path = os.path.join(path, item)
                    tree.append(f"{prefix}{'└── ' if is_last else '├── '}{item}")
                    if os.path.isdir(item_path):
                        dir_count += 1
                        sub_tree, sub_files, sub_dirs = build_tree(
                            item_path,
                            prefix + ('    ' if is_last else '│   '),
                            depth + 1
                        )
                        tree.append(sub_tree)
                        file_count += sub_files
                        dir_count += sub_dirs
                    else:
                        file_count += 1

                return '\n'.join(tree), file_count, dir_count
            except Exception as e:
                return f"Error reading directory: {str(e)}", 0, 0

        tree_structure, file_count, dir_count = build_tree(directory_path)

        return RecursiveDirectoryListing(
            path=directory_path,
            structure=tree_structure,
            file_count=file_count,
            directory_count=dir_count
        ).model_dump()
    except Exception as e:
        return RecursiveDirectoryListing(
            path=directory_path,
            structure="",
            file_count=0,
            directory_count=0,
            error=str(e)
        ).model_dump()

#エントリポイント
if __name__ == "__main__":
    async def main():
        logger.info("FS MCP Server starting...")
        logger.info(f"Operating System : {SYSTEM}")
        logger.info(f"Project Root : {PROJECT_ROOT}")
        logger.info(f"Default Dir : {DEFAULT_BASE_DIR}")
        try:
            await mcp.run_async(
                transport="streamable-http",
                host="0.0.0.0",
                port=4000,
                path="/mcp",
                log_level="info"
            )
        except Exception as e:
            print(f" Server startup failed: {e}")
            raise

    asyncio.run(main())