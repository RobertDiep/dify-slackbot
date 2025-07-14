import logging

from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from slack_sdk import WebClient
from markdown_to_mrkdwn import SlackMarkdownConverter

logger = logging.getLogger(__name__)

class NwSlackpostTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            bot_token = self.runtime.credentials['bot_token']
        except KeyError:
            raise Exception("Slack bot token not configured")

        channel = tool_parameters.get("channel_id")
        content = tool_parameters.get("content")
        markdown = tool_parameters.get("markdown", True)
        thread = tool_parameters.get("thread_ts", None)

        if not channel or not content:
            raise Exception("Channel or content is empty, cannot post empty content to empty channel.")

        msg = content
        if markdown:
            converter = SlackMarkdownConverter()
            msg = converter.convert(content)
            logger.debug(f"Converted {content[:20]}.. to markdown {msg[:20]}")

        try:
            webclient = WebClient(token=bot_token)

            if thread is not None:
                logger.debug(f"Sending message to {channel} in thread {thread}")
                msg = webclient.chat_postMessage(
                    channel=channel,
                    text=msg,
                    thread_ts=thread
                )
            else:
                logger.debug(f"Sending message to {channel}")
                msg = webclient.chat_postMessage(
                    channel=channel,
                    text=msg
                )

            yield self.create_variable_message("msg_ts", msg["ts"])

        except Exception as e:
            yield self.create_text_message(f"Failed to send message {str(e)}")

        yield self.create_text_message("Message sent succesfully")
