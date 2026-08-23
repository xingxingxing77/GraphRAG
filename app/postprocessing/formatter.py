"""
输出格式化器。

对最终答案进行格式化处理（Markdown、代码块高亮等）。
"""


class OutputFormatter:
    """输出格式化器。

    对生成的答案进行最终的格式化处理。
    """

    @staticmethod
    def format_markdown(text: str) -> str:
        """格式化为 Markdown。

        Args:
            text: 原始答案文本。

        Returns:
            格式化后的 Markdown 文本。
        """
        # TODO: 确保 Markdown 格式正确
        # TODO: 处理代码块高亮
        raise NotImplementedError

    @staticmethod
    def add_citation_links(text: str, citations: list[dict]) -> str:
        """在答案中插入引用链接。

        Args:
            text: 答案文本。
            citations: 引用信息列表。

        Returns:
            带有引用标注的答案文本。
        """
        # TODO: 将 [1][2] 等标注替换为可点击的链接
        raise NotImplementedError
