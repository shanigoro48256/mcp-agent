#search_mcp_server.py
import asyncio
import os
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from fastmcp import FastMCP
import httpx
from pydantic import BaseModel, Field
from tavily import TavilyClient
from logger_utils import get_logger

#環境変数読み込み
load_dotenv()

logger = get_logger(__name__)

# Web検索APIクライアント
class WebSearchClient:
    def __init__(self, api_key: Optional[str] = None):
        """Tavily APIクライアントの初期化"""
        logger.info("Initializing WebSearchClient")
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self.client = None

        if self.api_key:
            try:
                self.client = TavilyClient(api_key=self.api_key)
                logger.info("Tavily client initialized (prefix: %s...)", self.api_key[:10])
            except Exception as e:
                print(f"Failed to initialize Tavily client: {e}")
                logger.error(f"Failed to initialize Tavily client: {e}")
                self.client = None
        else:
            print("TAVILY_API_KEY not configured - Web search will be disabled")
            print("   Please set TAVILY_API_KEY in your .env file")
            logger.warning("TAVILY_API_KEY not configured - Web search will be disabled")
            
    def search(self, query: str, **kwargs) -> Dict[str, Any]:
        """検索結果の一覧を取得"""
        if not self.client:
            raise RuntimeError("Tavily client not initialized")
        result = self.client.search(query=query, **kwargs)
        return result
        
    def get_search_context(self, query: str, **kwargs) -> str:
        """検索クエリに対する要約"""
        if not self.client:
            raise RuntimeError("Tavily client not initialized")
        context = self.client.get_search_context(query=query, **kwargs)
        return context
        
    def qna_search(self, query: str, **kwargs) -> str:
        """検索クエリに対するQA回答"""
        if not self.client:
            raise RuntimeError("Tavily client not initialized")
        answer = self.client.qna_search(query=query, **kwargs)
        return answer


# GitHub APIクライアント
class GitHubClient:
    def __init__(self, token: Optional[str] = None):
        """Github APIクライアントの初期化"""
        logger.info("Initializing GitHubClient")
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-MCP-Server/1.0"
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"
            logger.info("GitHub Token configured (prefix: %s...)", self.token[:10])
        else:
            print("GitHub Token not configured - API rate limits will be very low")
            logger.warning("GitHub Token not configured - API rate limits will be very low")
            
    async def search_repositories(self, query: str, sort: str = "stars", order: str = "desc", per_page: int = 10) -> Dict[str, Any]:
        """リポジトリの検索"""
        async with httpx.AsyncClient() as client:
            params = {"q": query, "sort": sort, "order": order, "per_page": per_page}
            response = await client.get(f"{self.base_url}/search/repositories", headers=self.headers, params=params)
            if response.status_code == 403:
                remaining = response.headers.get("X-RateLimit-Remaining", "0")
                reset_time = response.headers.get("X-RateLimit-Reset", "Unknown")
                raise Exception(f"GitHub API rate limit exceeded. Remaining: {remaining}, Reset: {reset_time}")
            response.raise_for_status()
            data = response.json()
            return data

    async def search_code(self, query: str, per_page: int = 10) -> Dict[str, Any]:
        """コードの検索"""
        async with httpx.AsyncClient() as client:
            params = {"q": query, "per_page": per_page}
            response = await client.get(f"{self.base_url}/search/code", headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            return data

    async def search_issues(self, query: str, sort: str = "created", order: str = "desc", per_page: int = 10) -> Dict[str, Any]:
        """イシューの検索"""
        async with httpx.AsyncClient() as client:
            params = {"q": query, "sort": sort, "order": order, "per_page": per_page}
            response = await client.get(f"{self.base_url}/search/issues", headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            return data
            
    async def get_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """特定のGitHubリポジトリの詳細情報を取得"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/repos/{owner}/{repo}", headers=self.headers)
            response.raise_for_status()
            data = response.json()
            return data

    async def get_repository_contents(self, owner: str, repo: str, path: str = "") -> Dict[str, Any]:
        """リポジトリ内のファイルやディレクトリの一覧を取得"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/repos/{owner}/{repo}/contents/{path}", headers=self.headers)
            response.raise_for_status()
            data = response.json()
            return data

# arXiv APIクライアント（論文検索データベース）
class ArxivClient:
    """arXiv APIクライアントの初期化"""
    def __init__(self):
        logger.info("Initializing ArxivClient")
        self.base_url = "https://export.arxiv.org/api/query"
        self.headers = {"User-Agent": "arXiv-MCP-Server/1.0"}
        logger.info("arXiv client initialized")

        self.valid_sort_by = {
            "relevance": "relevance",
            "lastUpdatedDate": "lastUpdatedDate",
            "submittedDate": "submittedDate",
            "recent": "submittedDate"
        }
        self.valid_sort_order = {
            "ascending": "ascending",
            "descending": "descending",
            "asc": "ascending",
            "desc": "descending",
            "ASC": "ascending",
            "DESC": "descending"
        }

    async def search_papers(self, query: str, max_results: int = 10, start: int = 0,
                            sort_by: str = "relevance", sort_order: str = "descending") -> Dict[str, Any]:
        """キーワードから論文検索"""
        async with httpx.AsyncClient(follow_redirects=True) as client:
            params = {"search_query": query, "start": start, "max_results": max_results}
            if sort_by in self.valid_sort_by:
                actual_sort_by = self.valid_sort_by[sort_by]
                if actual_sort_by != "relevance":
                    params["sortBy"] = actual_sort_by
                    if sort_order in self.valid_sort_order:
                        params["sortOrder"] = self.valid_sort_order[sort_order]
                    else:
                        print(f"Warning: Invalid sort_order '{sort_order}'. Using 'descending'.")
                        params["sortOrder"] = "descending"
            else:
                print(f"Warning: Invalid sort_by '{sort_by}'. Using 'relevance'.")
            response = await client.get(self.base_url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            data = self._parse_arxiv_response(response.content)
            return data

    async def get_papers_by_ids(self, id_list: List[str]) -> Dict[str, Any]:
        """arXiv IDから論文情報取得"""
        async with httpx.AsyncClient() as client:
            params = {"id_list": ",".join(id_list)}
            response = await client.get(self.base_url, headers=self.headers, params=params, timeout=30)
            response.raise_for_status()
            data = self._parse_arxiv_response(response.content)
            return data

    def _parse_arxiv_response(self, xml_content: bytes) -> Dict[str, Any]:
        """検索結果全体のメタ情報を抽出（総検索数、論文の一覧など）"""
        root = ET.fromstring(xml_content)
        namespaces = {
            'atom': 'http://www.w3.org/2005/Atom',
            'opensearch': 'http://a9.com/-/spec/opensearch/1.1/',
            'arxiv': 'http://arxiv.org/schemas/atom'
        }
        total_results = root.find('.//opensearch:totalResults', namespaces)
        start_index = root.find('.//opensearch:startIndex', namespaces)
        items_per_page = root.find('.//opensearch:itemsPerPage', namespaces)
        papers = []
        for entry in root.findall('.//atom:entry', namespaces):
            paper = self._parse_paper_entry(entry, namespaces)
            if paper:
                papers.append(paper)
        return {
            "total_results": int(total_results.text) if total_results is not None else 0,
            "start_index": int(start_index.text) if start_index is not None else 0,
            "items_per_page": int(items_per_page.text) if items_per_page is not None else 0,
            "papers": papers
        }

    def _parse_paper_entry(self, entry, namespaces) -> Optional[Dict[str, Any]]:
        """検索された論文ごとのメタ情報を抽出（著者名、所属、PDFリンクなど）"""
        try:
            title = entry.find('atom:title', namespaces)
            id_elem = entry.find('atom:id', namespaces)
            published = entry.find('atom:published', namespaces)
            updated = entry.find('atom:updated', namespaces)
            summary = entry.find('atom:summary', namespaces)
            authors = []
            for author in entry.findall('atom:author', namespaces):
                name = author.find('atom:name', namespaces)
                affiliation = author.find('arxiv:affiliation', namespaces)
                authors.append({
                    "name": name.text if name is not None else "",
                    "affiliation": affiliation.text if affiliation is not None else ""
                })
            categories = [c.get('term', '') for c in entry.findall('atom:category', namespaces)]
            primary_category = entry.find('arxiv:primary_category', namespaces)
            links = {}
            for link in entry.findall('atom:link', namespaces):
                rel = link.get('rel', '')
                title_attr = link.get('title', '')
                href = link.get('href', '')
                if rel == 'alternate':
                    links['abstract'] = href
                elif rel == 'related' and title_attr == 'pdf':
                    links['pdf'] = href
                elif rel == 'related' and title_attr == 'doi':
                    links['doi'] = href
            comment = entry.find('arxiv:comment', namespaces)
            journal_ref = entry.find('arxiv:journal_ref', namespaces)
            doi = entry.find('arxiv:doi', namespaces)
            arxiv_id = id_elem.text.replace('http://arxiv.org/abs/', '') if id_elem is not None else ""
            return {
                "id": arxiv_id,
                "title": title.text.strip() if title is not None else "",
                "authors": authors,
                "published": published.text if published is not None else "",
                "updated": updated.text if updated is not None else "",
                "summary": summary.text.strip() if summary is not None else "",
                "categories": categories,
                "primary_category": primary_category.get('term', '') if primary_category is not None else "",
                "links": links,
                "comment": comment.text if comment is not None else "",
                "journal_ref": journal_ref.text if journal_ref is not None else "",
                "doi": doi.text if doi is not None else ""
            }
        except Exception as e:
            print(f"Error parsing paper entry: {e}")
            return None

# MCPサーバのインスタンス化
mcp = FastMCP("Search MCP Server")

# クライアントのインスタンス化
logger.info("Initializing WebSearchClient, GitHubClient, ArxivClient")
web_search_client = WebSearchClient()
github_client = GitHubClient()
arxiv_client = ArxivClient()

# 検索結果の出力構造を定義
class WebSearchResult(BaseModel):
    results: List[Dict[str, Any]] = Field(description="Web検索結果")
    total_results: int = Field(description="総検索結果数")
    query: str = Field(description="検索クエリ")

class GithubSearchResult(BaseModel):
    total_count: int = Field(description="総数")
    items: List[Dict[str, Any]] = Field(description="検索結果")

class ArxivSearchResult(BaseModel):
    total_results: int = Field(description="総検索結果数")
    start_index: int = Field(description="開始インデックス")
    items_per_page: int = Field(description="ページあたりの件数")
    papers: List[Dict[str, Any]] = Field(description="論文リスト")

#mcp toolの定義
## mcp.toolデコレータ：MCPクライアントからツールを呼び出す。name,description,tagsを参照
@mcp.tool(
    name="web_search",
    description="Tavily Search APIを使用してリアルタイムWeb検索を実行し、関連性の高い構造化された検索結果を取得します",
    tags={"web", "search", "tavily", "realtime"}
)
async def web_search(
    query: str,
    max_results: int = 3,
    search_depth: str = "basic",
    include_answer: bool = False,
    include_images: bool = False,
    include_raw_content: bool = False,
    country: Optional[str] = None,
    topic: str = "general"
) -> WebSearchResult:
    if not web_search_client.client:
        return WebSearchResult(
            results=[{"error": "Tavily client not initialized. Please check TAVILY_API_KEY."}],
            total_results=0,
            query=query
        )

    try:
        # パラメータの検証
        max_results = min(max(max_results, 1), 20)
        if search_depth not in ["basic", "advanced"]:
            search_depth = "basic"
        if topic not in ["general", "news"]:
            topic = "general"
        
        # 検索実行
        search_params = {
            "query": query,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": include_answer,
            "include_images": include_images,
            "include_raw_content": include_raw_content,
            "topic": topic
        }
        if country:
            search_params["country"] = country
        
        response = web_search_client.search(**search_params)
        
        # レスポンスの整形
        results = []
        for result in response.get("results", []):
            formatted_result = {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "content": result.get("content", ""),
                "score": result.get("score", 0.0),
                "published_date": result.get("published_date", "")
            }
            if include_raw_content and "raw_content" in result:
                formatted_result["raw_content"] = result["raw_content"][:1000]
            results.append(formatted_result)

        # 回答の処理
        if include_answer and "answer" in response:
            results.insert(0, {
                "type": "answer",
                "content": response["answer"],
                "title": "AI Generated Answer",
                "url": "",
                "score": 1.0
            })
        
        # 画像の処理
        if include_images and "images" in response:
            image_results = []
            for img in response["images"][:3]:
                if isinstance(img, dict):
                    image_results.append({
                        "type": "image",
                        "url": img.get("url", ""),
                        "description": img.get("description", "")
                    })
                else:
                    image_results.append({
                        "type": "image",
                        "url": img,
                        "description": ""
                    })
            results.extend(image_results)
        
        total = len(results)
        return WebSearchResult(
            results=results,
            total_results=total,
            query=query
        )
        
    except Exception as e:
        return WebSearchResult(
            results=[{"error": f"Web search failed: {str(e)}"}],
            total_results=0,
            query=query
        )

@mcp.tool(
    name="web_search_context",
    description="複数のソースから取得した情報を要約しコンテキスト文字列を生成します",
    tags={"web", "search", "context", "summary", "tavily"}
)
async def web_search_context(
    query: str,
    max_results: int = 3,
    search_depth: str = "advanced"
) -> Dict[str, Any]:
    if not web_search_client.client:
        return {"error": "Tavily client not initialized"}

    try:
        context = web_search_client.get_search_context(
            query=query,
            max_results=max_results,
            search_depth=search_depth
        )
        return {
            "query": query,
            "context": context,
            "length": len(context),
            "word_count": len(context.split())
        }
    except Exception as e:
        return {"error": f"Context search failed: {str(e)}"}

@mcp.tool(
    name="web_search_qna",
    description="質問に対する簡潔で正確な回答をTavily Search APIで生成します。検索結果に基づいてLLMが質問への直接的な回答を生成します。",
    tags={"web", "search", "qna", "answer","tavily"}
)
async def web_search_qna(
    query: str,
    max_results: int = 3
) -> Dict[str, Any]:
    logger.info(f"web_search_qna called with query={query!r}, max_results={max_results}")
    if not web_search_client.client:
        return {"error": "Tavily client not initialized"}

    try:
        answer = web_search_client.qna_search(
            query=query,
            max_results=max_results
        )
        return {
            "query": query,
            "answer": answer,
            "length": len(answer),
            "word_count": len(answer.split())
        }
    except Exception as e:
        return {"error": f"QnA search failed: {str(e)}"}

# GitHub関連のツール
@mcp.tool(
    name="search_github_repositories",
    description="GitHub上のリポジトリを検索し、スター数やフォーク数などの詳細情報を取得します。",
    tags={"search", "github", "repositories"}
)
async def search_github_repositories(
    query: str,
    sort: str = "stars",
    order: str = "desc",
    per_page: int = 10
) -> GithubSearchResult:
    try:
        result = await github_client.search_repositories(query, sort, order, per_page)
        return GithubSearchResult(
            total_count=result["total_count"],
            items=[
                {
                    "full_name": item["full_name"],
                    "description": item.get("description"),
                    "stars": item.get("stargazers_count"),
                    "forks": item.get("forks_count"),
                    "language": item.get("language"),
                    "topics": item.get("topics"),
                    "html_url": item.get("html_url"),
                }
                for item in result["items"]
            ]
        )
    except Exception as e:
        raise Exception(f"Repository search failed: {str(e)}")

@mcp.tool(
    name="search_github_code",
    description="GitHub上のファイル内容からコードを検索し、該当するファイルの情報とリポジトリ詳細を取得します",
    tags={"search", "github", "code"}
)
async def search_github_code(
    query: str,
    per_page: int = 10
) -> GithubSearchResult:
    try:
        result = await github_client.search_code(query, per_page)
        return GithubSearchResult(
            total_count=result["total_count"],
            items=result["items"]
        )
    except Exception as e:
        raise Exception(f"Code search failed: {str(e)}")

@mcp.tool(
    name="search_github_issues",
    description="GitHub上のイシューやプルリクエストを検索します",
    tags={"search", "github", "issues","pull-requests", "bugs"}
)
async def search_github_issues(
    query: str,
    sort: str = "created",
    order: str = "desc",
    per_page: int = 10
) -> GithubSearchResult:
    try:
        result = await github_client.search_issues(query, sort, order, per_page)
        return GithubSearchResult(
            total_count=result["total_count"],
            items=result["items"]
        )
    except Exception as e:
        raise Exception(f"Issue search failed: {str(e)}")

@mcp.tool(
    name="get_github_repository",
    description="特定のGitHubリポジトリの詳細情報を取得します",
    tags={"github", "repository", "info", "details"}
)
async def get_github_repository(
    owner: str,
    repo: str
) -> Dict[str, Any]:
    try:
        result = await github_client.get_repository(owner, repo)
        return result
    except Exception as e:
        raise Exception(f"Repository info fetch failed: {str(e)}")

@mcp.tool(
    name="get_github_repository_contents",
    description="GitHubリポジトリ内のファイルとディレクトリ構造を取得します",
    tags={"github", "repository", "contents", "files", "structure"}
)
async def get_github_repository_contents(
    owner: str,
    repo: str,
    path: str = ""
) -> Dict[str, Any]:
    try:
        result = await github_client.get_repository_contents(owner, repo, path)
        return result
    except Exception as e:
        raise Exception(f"Repository contents fetch failed: {str(e)}")

# arXiv論文のツール
@mcp.tool(
    name="search_arxiv_papers",
    description="arXiv論文データベースから学術論文を検索します。キーワードで検索し、論文のタイトル、著者、要約、カテゴリ、公開日、PDF URLを取得します",
    tags={"search", "arxiv", "papers", "academic"}
)
async def search_arxiv_papers(
    query: str,
    max_results: int = 10,
    start: int = 0,
    sort_by: str = "relevance",
    sort_order: str = "descending",
    include_urls: bool = True,
    response_format: str = "detailed"
) -> ArxivSearchResult:
    try:
        max_results = min(max_results, 30)
        
        result = await arxiv_client.search_papers(
            query=query,
            max_results=max_results,
            start=start,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        formatted_papers = []
        for paper in result["papers"]:
            if response_format in ["detailed", "urls_first"] and include_urls:
                formatted_paper = {
                    "論文ID": paper["id"],
                    "PDF": paper["links"].get("pdf", "unavaliable"),
                    "要約URL": paper["links"].get("abstract", "unavaliable"),
                    "タイトル": paper["title"],
                    "著者": ", ".join([author["name"] for author in paper["authors"]]),
                    "公開日": paper["published"][:10],
                    "要約": paper["summary"][:200] + "..." if len(paper["summary"]) > 200 else paper["summary"],
                    "カテゴリ": ", ".join(paper["categories"])
                }
            else:
                formatted_paper = {
                    "id": paper["id"],
                    "title": paper["title"],
                    "authors": [author["name"] for author in paper["authors"]],
                    "summary": paper["summary"][:200] + "..." if len(paper["summary"]) > 200 else paper["summary"]
                }
            
            formatted_papers.append(formatted_paper)
        return ArxivSearchResult(
            total_results=result["total_results"],
            start_index=result["start_index"],
            items_per_page=result["items_per_page"],
            papers=formatted_papers
        )
    except Exception as e:
        raise Exception(f"arXiv search failed: {str(e)}")

# ステータス確認ツール
@mcp.tool(name="server_status")
async def server_status() -> Dict[str, Any]:
    """全サーバーの状態を確認"""
    logger.debug("Checking overall server status")
    status = {
        "server_name": "MCP Unified Search Server",
        "services": {}
    }
    
    # Web Search Status
    web_search_status = "Client initialized" if web_search_client.client else "Client not initialized"
    logger.debug(f"Web Search status: {web_search_status}")
    status["services"]["web_search"] = {
        "status": web_search_status,
        "api_key_configured": bool(web_search_client.api_key)
    }
    
    # GitHub Status
    github_status = "Token configured" if github_client.token else "Token not configured"
    logger.debug(f"GitHub status: {github_status}")
    status["services"]["github"] = {
        "status": github_status,
        "rate_limit_info": "Check with GitHub API for current limits"
    }
    
    # arXiv Status
    try:
        await arxiv_client.search_papers("test", max_results=1)
        arxiv_status = "Connection successful"
        logger.debug("arXiv connection successful")
    except Exception as e:
        arxiv_status = f"Connection failed: {str(e)}"
        logger.warning(f"arXiv connection failed: {e}")
    
    status["services"]["arxiv"] = {
        "status": arxiv_status
    }
    
    return status

# エントリポイント
if __name__ == "__main__":
    async def main():
        logger.info("Search MCP Server starting...")
        logger.info(f"Web Search: {'available' if web_search_client.client else 'unavailable'}")
        logger.info(f"GitHub: {'available' if github_client.token else 'unavailable'}")
        logger.info("arXiv: available")
    
        try:
            """MCPサーバーを起動し、HTTPストリームでツール呼び出しを受け付け"""
            await mcp.run_async(
                transport="streamable-http",
                host="0.0.0.0",
                port=1000,
                path="/mcp",
                log_level="info"
            )
        except Exception as e:
            logger.error(f"Server startup failed: {e}")
            raise
    asyncio.run(main())