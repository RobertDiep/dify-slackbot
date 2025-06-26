import logging.handlers
from dify_plugin import Plugin, DifyPluginEnv
import dify_plugin
import logging
import sys


plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120))

if __name__ == "__main__":
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logging.getLogger("concurrent").setLevel(logging.WARN)
    logging.getLogger("httpcore").setLevel(logging.WARN)
    logging.getLogger("httpx").setLevel(logging.WARN)
    logging.getLogger("requests").setLevel(logging.WARN)
    logging.getLogger("slack_bolt").setLevel(logging.WARN)
    logging.getLogger("urllib3").setLevel(logging.WARN)
    logging.getLogger("slack_sdk").setLevel(logging.WARN)
    logging.getLogger("dify_plugin.core.server.tcp.request_reader").setLevel(
        logging.WARN
    )

    formatter = logging.Formatter("%(levelname)s:%(name)s:%(funcName)s - %(message)s")
    logger_handler = logging.FileHandler("./applog.log")
    logger_handler.setFormatter(formatter)
    print(logger.handlers)
    print(logging.getHandlerNames())
    logger.addHandler(logger_handler)
    logging.info(f"dify_plugin version: {dify_plugin.__spec__}")

    plugin.run()
