"""Agent 流式 — 简化版：ThreadPoolExecutor + 队列推送 SSE

后台线程跑 LLMService.run()，事件通过 queue.Queue 推送给 SSE。
"""
import json
import queue
import threading
import time
from decimal import Decimal
from typing import AsyncGenerator

from agent.llm_service import LLMService, generate_analysis, generate_predict, cache_result
from langchain_openai import ChatOpenAI
from config import LLM_CONFIG


def make_streaming_llm(label: str = "", temp: float = 0.0, max_tokens: int = 1024) -> ChatOpenAI:
    """创建 LLM 实例（multi_agent 流水线复用；支持流式与普通 invoke）"""
    return ChatOpenAI(
        model=LLM_CONFIG["model"],
        api_key=LLM_CONFIG["api_key"],
        base_url=LLM_CONFIG["base_url"],
        temperature=temp,
        max_tokens=max_tokens,
    )


class _JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        return super().default(obj)


def _sse(event: str, data: dict) -> str:
    payload = json.dumps({'type': event, **data}, ensure_ascii=False, cls=_JSONEncoder)
    return f"data:{payload}\n\n"


async def ask_stream(query: str, history: list[dict] | None = None) -> AsyncGenerator[str, None]:
    """流式执行：后台线程跑 LLMService，主协程轮询队列发 SSE"""
    event_queue: queue.Queue = queue.Queue()
    service = LLMService(query, history)

    def _bg_runner():
        try:
            for event in service.run():
                event_queue.put(event)
        except Exception as e:
            event_queue.put({"type": "error", "message": str(e)})
        finally:
            event_queue.put(None)  # 结束信号

    thread = threading.Thread(target=_bg_runner, daemon=True)
    thread.start()

    t0 = time.time()

    while True:
        item = event_queue.get()
        if item is None:
            break
        yield _sse(item["type"], {k: v for k, v in item.items() if k != "type"})

    # 缓存结果供后续分析/预测复用
    if service.sql_result.get("rows"):
        cache_result(query, service.sql, service.sql_result, service.schema_context)

    thread.join(timeout=1)


async def analysis_stream(sql: str, query: str, sql_result: dict) -> AsyncGenerator[str, None]:
    """独立分析流式端点"""
    try:
        for event in generate_analysis(query, sql, sql_result):
            yield _sse(event["type"], {k: v for k, v in event.items() if k != "type"})
    except Exception as e:
        yield _sse("error", {"content": str(e)})


async def predict_stream(sql_result: dict) -> AsyncGenerator[str, None]:
    """独立预测流式端点"""
    try:
        for event in generate_predict(sql_result):
            yield _sse(event["type"], {k: v for k, v in event.items() if k != "type"})
    except Exception as e:
        yield _sse("error", {"content": str(e)})
