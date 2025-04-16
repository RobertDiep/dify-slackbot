import logging


class SlackbotPluginLoggerFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return f"{record.levelname}:{record.filename}:{record.funcName}: {record.message}"
