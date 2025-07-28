# llm_utils.py
import os
from enum import Enum
from typing import Optional, List
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from logger_utils import get_logger

class LLMType(Enum):
    OLLAMA = "ollama"

def create_llm(llm_type: LLMType) -> Optional[BaseChatModel]:
    """
    Qwen3:30BでVRAM 24GB程度
    qwen3:8b、deepseek-r1:32bのモデルで動作確認済
    """
    if llm_type == LLMType.OLLAMA:
        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "qwen3:30b-a3b"),
            temperature=0.1,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    logger.error(f"Unsupported LLM type: {llm_type}")
    return None

async def chat(
    messages: List[HumanMessage | SystemMessage],
    llm_type: LLMType = LLMType.OLLAMA,
) -> str:
    llm = create_llm(llm_type)
    if not llm:
        return "LLM initialization failed."
    try:
        resp = await llm.ainvoke(messages)
        return str(resp.content)
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return f"LLM error: {e}"
