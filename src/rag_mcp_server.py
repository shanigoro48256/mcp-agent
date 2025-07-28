#rag_mcp_server.py
from __future__ import annotations
import asyncio
import functools
import os
import pathlib
from typing import List, Optional, Tuple, Union
import numpy as np
from dotenv import load_dotenv
from langchain_community.document_loaders import WebBaseLoader
from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import maximal_marginal_relevance
from langchain.text_splitter import CharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from fastmcp import FastMCP
from llm_utils import LLMType, create_llm
from logger_utils import get_logger

#環境変数読み込み
load_dotenv()

logger = get_logger(__name__)

#RAG用WEBページ
URLS = [
    "https://ja.wikipedia.org/wiki/もののけ姫",
    "https://ja.wikipedia.org/wiki/千と千尋の神隠し",
    "https://ja.wikipedia.org/wiki/風の谷のナウシカ",
]

RAG_SYSTEM_PROMPT = (
    "あなたは、与えられたコンテキストにもとづき正確な情報を提供する有能なアシスタントです。"
    "ユーザーの質問には必ずそのコンテキスト内の情報だけを使って回答してください。"
    "十分な情報が含まれていない場合は、その旨をはっきり伝えてください。"
    "回答は簡潔かつ事実ベースで、必要に応じてコンテキストの該当部分を引用してください。"
)

INDEX_DIR = pathlib.Path(os.getenv("FAISS_DIR", "faiss_index"))

# RAGの構築
@functools.lru_cache(maxsize=1)
def _get_embeddings():
    """埋め込みモデルの読み込み"""
    logger.info("Loading multilingual embedding model...")
    return HuggingFaceEmbeddings(model_name="intfloat/multilingual-e5-large")

async def create_rag(links: Optional[List[str]] = None) -> FAISS:
    """URLからドキュメントを収集し、ベクトルストアを構築"""
    urls = links or URLS
    if not urls:
        raise ValueError("URLが指定されていません。")

    if (INDEX_DIR / "index.faiss").exists():
        logger.info("Loading existing FAISS index")
        return FAISS.load_local(
            INDEX_DIR,
            embeddings=_get_embeddings(),
            allow_dangerous_deserialization=True,
        )

    logger.info(f"Fetching {len(urls)} URLs...")
    docs: List[Document] = sum((WebBaseLoader(u).load() for u in urls), [])
    if not docs:
        raise RuntimeError("Failed to load documents")

    splitter = CharacterTextSplitter.from_tiktoken_encoder(
        separator="\n", chunk_size=1_000, chunk_overlap=100
    )
    chunks = splitter.split_documents(docs)
    logger.info(f"Split into {len(chunks)} chunks.")

    vs = FAISS.from_documents(chunks, embedding=_get_embeddings())
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    vs.save_local(INDEX_DIR)
    logger.info("FAISS index has been saved")
    return vs

async def get_relevant_documents(
    query: str,
    vectorstore: FAISS,
    num_documents: int = 4,
    fetch_k: int = 20,
    lambda_mult: float = 0.7,
) -> List[Document]:
    """ベクトル検索を行いクエリに対して関連性のあるドキュメントを抽出する"""
    embeddings = vectorstore.embeddings
    query_emb = embeddings.embed_query(query)

    try:
        docs_and_scores = vectorstore.similarity_search_with_score_by_vector(
            query_emb, k=fetch_k
        )
        docs = [doc for doc, _ in docs_and_scores]
    except AttributeError:
        docs = vectorstore.similarity_search(query, k=fetch_k)

    if len(docs) > num_documents:
        doc_embs = [embeddings.embed_query(d.page_content) for d in docs]
        idxs = maximal_marginal_relevance(
            np.array(query_emb), np.array(doc_embs),
            k=num_documents, lambda_mult=lambda_mult
        )
        return [docs[i] for i in idxs]
    return docs


async def generate_response_from_docs(
    query: str,
    documents: List[Document],
    llm_type: LLMType,
    system_prompt: str,
) -> str:
    """ベクトルストアから抽出した関連情報をもとにLLMで回答生成"""
    llm = create_llm(llm_type)
    if llm is None:
        return "\n\n".join([doc.page_content for doc in documents])

    context = "\n\n".join(
        f"Document {i+1}:\n{doc.page_content}"
        for i, doc in enumerate(documents)
    )
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"CONTEXT:\n{context}\n\nQUESTION:\n{query}")
    ]

    try:
        res = await llm.ainvoke(messages)
        return str(res.content)
    except Exception as e:  # pylint: disable=broad-except
        return f"応答生成エラー: {e}"


async def search_rag(
    query: str,
    vectorstore: FAISS,
    llm_type: LLMType = LLMType.OLLAMA,
    num_documents: int = 5,
    fetch_k: int = 20,
    lambda_mult: float = 0.7,
    return_source_documents: bool = False,
) -> Union[str, Tuple[str, List[Document]]]:
    """RAGで検索しLLMで回答を生成（get_relevant_documents->generate_response_from_docs）"""
    docs = await get_relevant_documents(
        query, vectorstore, num_documents, fetch_k, lambda_mult
    )
    if not docs:
        msg = "該当する情報が見つかりませんでした。"
        return (msg, []) if return_source_documents else msg

    response = await generate_response_from_docs(
        query=query,
        documents=docs,
        llm_type=llm_type,
        system_prompt=RAG_SYSTEM_PROMPT,
    )
    return (response, docs) if return_source_documents else response

# ベクトルストアの初期化
vectorstore: Optional[FAISS] = None
_initialization_lock = asyncio.Lock()
_is_initialized = False

async def initialize_resources():
    """ベクトルストアの初期化"""
    global vectorstore, _is_initialized
    async with _initialization_lock:
        if _is_initialized:
            return
        logger.info("Initializing server resources...")
        vectorstore = await create_rag()
        _is_initialized = True
        logger.info("All server resources initialized successfully")

# FastMCPインスタンス化
mcp = FastMCP("RAG MCP Server")

#mcp toolの定義
@mcp.tool(
    name="rag_search",
    description="もののけ姫、千と千尋の神隠し、風の谷のナウシカについて、RAG検索します",
    tags={"search", "rag", "mononokehime", "sentochihiro", "naushika"},
)
async def rag_search(
    query: str,
    num_documents: int = 5,
    return_sources: bool = False,
) -> str:
    if not _is_initialized or vectorstore is None:
        return "RAG system not initialized. Please restart the server."
    answer = await search_rag(
        query=query,
        vectorstore=vectorstore,
        llm_type=LLMType.OLLAMA,
        num_documents=num_documents,
        return_source_documents=return_sources,
    )
    if return_sources and isinstance(answer, tuple):
        resp, docs = answer
        srcs = "\n".join(
            f"- {d.metadata.get('title','無題')} ({d.metadata.get('source','URL不明')})"
            for d in docs
        )
        return resp + "\n\n参考文献\n" + srcs
    return answer if isinstance(answer, str) else str(answer)

@mcp.tool(name="rag_status")
async def rag_status() -> str:
    """現在のベクトルストアの状態を返す"""
    total = vectorstore.index.ntotal if vectorstore else 0
    return f"RAG ready. chunks={total}"

# エントリポイント
if __name__ == "__main__":
    async def main():
        logger.info("RAG MCP server starting...")
        await initialize_resources()
        await mcp.run_async(
            transport="streamable-http",
            host="0.0.0.0",
            port=2000,
            path="/mcp",
            log_level="info",
        )
    asyncio.run(main())