from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


class LogSyntaxHighlighter(QSyntaxHighlighter):
    """Color complete log rows by severity and highlight search matches."""

    LEVEL_COLORS = {
        "DEBUG": "#8b95a7",
        "INFO": "#35c77a",
        "WARNING": "#f2c94c",
        "ERROR": "#ff5c5c",
        "CRITICAL": "#ff3b6b",
    }

    def __init__(self, document):
        super().__init__(document)
        self.colors_enabled = True
        self.search_term = ""

    @classmethod
    def format_for_level(cls, level: str) -> QTextCharFormat:
        result = QTextCharFormat()
        result.setForeground(QColor(cls.LEVEL_COLORS.get(level.upper(), cls.LEVEL_COLORS["DEBUG"])))
        if level.upper() in {"WARNING", "ERROR", "CRITICAL"}:
            result.setFontWeight(QFont.DemiBold)
        return result

    @staticmethod
    def level_for_text(text: str) -> str | None:
        for level in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"):
            if f"[{level}]" in text:
                return level
        return None

    def set_colors_enabled(self, enabled: bool) -> None:
        self.colors_enabled = enabled
        self.rehighlight()

    def set_search_term(self, term: str) -> None:
        self.search_term = term
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        level = self.level_for_text(text)
        if self.colors_enabled and level:
            self.setFormat(0, len(text), self.format_for_level(level))
        if self.search_term:
            expression = QRegularExpression(QRegularExpression.escape(self.search_term), QRegularExpression.CaseInsensitiveOption)
            iterator = expression.globalMatch(text)
            search_format = QTextCharFormat()
            search_format.setBackground(QColor("#315f9f"))
            search_format.setForeground(QColor("#ffffff"))
            search_format.setFontWeight(QFont.Bold)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), search_format)

