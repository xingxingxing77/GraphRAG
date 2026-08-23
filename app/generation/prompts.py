"""
Prompt 模板管理。

定义和管理各层使用的 Prompt 模板。
"""

# --- 第三方库 ---
from langchain_core.prompts import ChatPromptTemplate


# 生成层系统 Prompt
GENERATION_SYSTEM_PROMPT = """你是一个专业的知识助手。请严格基于以下提供的参考资料回答用户的问题。

规则：
1. 仅使用提供的参考资料中的信息来回答
2. 如果参考资料中没有足够的信息来回答问题，请明确说明"根据现有资料无法确定"
3. 在回答中使用 [1]、[2] 等标注引用来源
4. 不要编造参考资料中没有的信息

参考资料：
{evidence}
"""

# 查询改写 Prompt
QUERY_REWRITE_PROMPT = """请将以下用户查询改写为更精确的检索查询。
要求：保留核心意图，补充可能的关键词，去除口语化表达。

原始查询：{query}
"""

# 幻觉检测 Prompt
FAITHFULNESS_CHECK_PROMPT = """请判断以下答案是否忠实于提供的参考资料。
如果答案中的所有事实都能在参考资料中找到支撑，回答"忠实"；
如果答案包含参考资料中没有的信息，回答"不忠实"并指出具体位置。

参考资料：{evidence}
答案：{answer}
"""


def get_generation_prompt() -> ChatPromptTemplate:
    """获取生成层的 ChatPromptTemplate。

    Returns:
        ChatPromptTemplate: 配置好的 Prompt 模板。
    """
    return ChatPromptTemplate.from_messages([
        ("system", GENERATION_SYSTEM_PROMPT),
        ("human", "{query}"),
    ])
