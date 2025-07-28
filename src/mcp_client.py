#mcp_client.py
import os
import asyncio
import json
import uuid
from datetime import datetime
from dataclasses import dataclass
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from llm_utils import LLMType, create_llm
from typing import Annotated, TypedDict, List
from langgraph.graph.message import add_messages
from langgraph.managed import RemainingSteps
from langsmith import traceable
from langsmith.run_helpers import trace

#環境変数読み込み
load_dotenv()

# プロジェクト名を生成
PROJECT_NAME = os.getenv("LANGCHAIN_PROJECT", f"mcp-agent-{uuid.uuid4()}")

# LangGraphの状態（State）のデータ構造を定義
class State(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    remaining_steps: RemainingSteps

# BaseMessage オブジェクトから content（メッセージ本文）を取り出すヘルパー関数
def get_message_content(message: BaseMessage) -> str:
    return str(getattr(message, "content", ""))

# セッションID生成
def new_thread_id(user_id: str = "guest") -> str:
    return f"{user_id}-{uuid.uuid4()}"

# エージェント実行関数
@traceable(name="run_agent_session")
async def run_agent(agent, user_input: str, config: dict):
    user_msg = HumanMessage(content=user_input)

    with trace(name="agent_execution", inputs={"user_input": user_input}):
        response = await agent.ainvoke(
            {"messages": [user_msg], "remaining_steps": 5},
            config=config,
        )

    # ツール呼び出しログを出力
    if response and "messages" in response:
        msgs: List[BaseMessage] = response["messages"]
        last_user_idx = max(
            (i for i, m in enumerate(msgs) if isinstance(m, HumanMessage)), default=-1
        )

        i = last_user_idx + 1
        while i < len(msgs):
            m = msgs[i]
            if isinstance(m, AIMessage) and m.tool_calls:
                for tc in m.tool_calls:
                    print(f"[Tool Call] -> {tc['name']}({json.dumps(tc.get('args', {}), ensure_ascii=False)})")

                if i + 1 < len(msgs) and isinstance(msgs[i + 1], ToolMessage):
                    tool_msg: ToolMessage = msgs[i + 1]
                    print(f"[Tool Result] <- {tool_msg.content}")
                    i += 2
                    continue
            i += 1
    return response

# メインループ
@traceable(name="main_agent_session",project_name=PROJECT_NAME)
async def main():
    thread_id = new_thread_id(user_id=os.getenv("USER_ID", "guest"))
    config = {"configurable": {"thread_id": thread_id}}

    # MCPクライアントの初期化
    client = MultiServerMCPClient({
        "search_mcp_server":{"transport": "streamable_http", "url": "http://localhost:1000/mcp/"},
        "rag_mcp_server":   {"transport": "streamable_http", "url": "http://localhost:2000/mcp/"},
        "db_mcp_server":    {"transport": "streamable_http", "url": "http://localhost:3000/mcp/"},
        "fs_mcp_server":    {"transport": "streamable_http", "url": "http://localhost:4000/mcp/"},
    })

    try:
        # LLMの初期化
        llm = create_llm(LLMType.OLLAMA)
        if llm is None:
            raise RuntimeError("LLM初期化失敗")
        
        # MCP toolの取得
        tools = await client.get_tools()
        print(f"[Tools] -> Loaded {len(tools)} tools from MCP servers")

        # チェックポインター
        checkpointer = InMemorySaver()
        
        #LangGraphのReActエージェント初期化
        agent = create_react_agent(
            model=llm,
            tools=tools,
            state_schema=State,
            checkpointer=checkpointer,
            prompt=(
                "あなたは日本語で回答するAIアシスタントです。"
                "ユーザーの質問に対し、正確かつ簡潔に答えてください。"
                "必要に応じて、ツールを活用して情報を取得してください。"
            ),
        )

        print(f"MCP Agent Session: {thread_id}")
        print(f"LangSmith Project: {PROJECT_NAME}")
        print("終了するには 'exit' と入力してください。")

        while True:
            user_input = input("\n質問を入力: ").strip()
            if user_input.lower() in {"exit", "quit", "q"}:
                print("セッションを終了します。")
                break
            if not user_input:
                continue

            response = await run_agent(agent, user_input, config)
            if response:
                final = response["messages"][-1]
                print(f"応答: {final.content}")

    except KeyboardInterrupt:
        print("\n中断されました。")
    except Exception as e:
        print(f"エラーが発生しました: {e}")
    finally:
        print("セッションが終了しました。")

if __name__ == "__main__":
    asyncio.run(main())