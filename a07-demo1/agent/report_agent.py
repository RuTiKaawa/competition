"""报告生成 Agent — 流式 + 结构化输出 + 行业专家级分析"""

from typing import AsyncIterator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessageChunk
from config import LLM_CONFIG

REPORT_SYSTEM_PROMPT = """你是一位拥有20年经验的制造业数据分析专家，曾为华为、比亚迪、富士康等顶级制造企业提供咨询服务。

请按以下固定格式输出分析报告（严格遵循分隔符，使用纯文字，不要任何 markdown 标记符号）：

---执行摘要---
用2-3句话概括：整体状况概述、最关键的1个亮点、1个最大风险、核心建议方向。关键数字直接写在句中，不用任何加粗或特殊格式。用⚠️标记风险，✅标记亮点。

---生产质量分析---
分析各工序良率对比，明确指出瓶颈工序及其与行业标杆的差距（波峰焊行业标杆≥98.5%、SMT标杆≥99.2%）。分析不良类型的根因推断，结合工序间的关联。纯文字叙述，不用列表符号。

---库存与供应链---
评估库存健康度，列出预警产品及短缺比例。分析缺货对生产的影响。给出补货优先级建议。纯文字叙述。

---设备与产能---
分析产线产能利用率与平衡性。推断设备综合效率。识别非计划停机模式。纯文字叙述。

---改进建议---
按优先级给出3-5条可执行建议。每条包含：问题、措施、预期效果、实施难度（低/中/高）。优先给出投入少见效快的快赢方案。

禁止事项：
- 不要编造数据
- 不要说"数据不足无法分析"
- 禁止使用任何 markdown 格式符号（包括 **加粗**、- 列表、# 标题、> 引用等）
- 数字直接写在句子中，如"良率为97.19%"
- 不要输出分隔符以外的内容
"""


def _llm(temp: float = 0.3):
    return ChatOpenAI(
        model=LLM_CONFIG["model"],
        api_key=LLM_CONFIG["api_key"],
        base_url=LLM_CONFIG["base_url"],
        temperature=temp,
        max_tokens=LLM_CONFIG["max_tokens"],
    )


async def generate_report_stream(context: str) -> AsyncIterator[str]:
    """流式生成专家分析报告"""
    llm = _llm(temp=0.3)
    full_prompt = REPORT_SYSTEM_PROMPT
    async for chunk in llm.astream([
        SystemMessage(content=full_prompt),
        HumanMessage(content=f"请基于以下数据生成分析报告：\n\n{context}")
    ]):
        if isinstance(chunk, AIMessageChunk) and chunk.content:
            yield chunk.content
