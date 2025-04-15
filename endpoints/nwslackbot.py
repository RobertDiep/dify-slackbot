import logging
import sys
import json 
import time

from dify_plugin import Endpoint
from slack_sdk import WebClient
from collections.abc import Mapping
from werkzeug import Request, Response
from slack_bolt import App, Ack, Say

from .slack_utils import is_dm
from .slack_utils import SlackRequestHandler

class ConfigNotFound(Exception):
    pass

logging.basicConfig(level=logging.DEBUG, handlers=[logging.StreamHandler(sys.stdout)])

STORAGE_CONFIG_KEY = "config"

class NwSlackEndpoint(Endpoint):
    def __init__(self, session):
        super().__init__(session)

    def _invoke(self, r: Request, values: Mapping, settings: Mapping):
        logging.info("Incoming request")

        # set slack admins
        self._slack_admins = settings.get("slack_admin_ids").split(",")

        # try to get config from storage
        try:
            config = self.session.storage.get(STORAGE_CONFIG_KEY)
            self._slack_config = json.loads(config)
        except json.JSONDecodeError:
            self.session.storage.set(STORAGE_CONFIG_KEY, b"{}")
            config = None
            self._slack_config = None

        app = App(token=settings.get("bot_token"), signing_secret=settings.get("signing_secret"))

        app.event("app_mention")(ack=self.handle_ack, lazy=[self.handle_mention])
        app.event("message")(self.handle_dm)

        handler = SlackRequestHandler(app)
        logging.debug("_invoke:return")
        return handler.handle(r)

    def handle_ack(self, body: dict, say: Say, ack: Ack):
        logging.debug("handle_ack")
        msg_ts = body["event"]["ts"]
        say("Got message, starting workflow", thread_ts=msg_ts)

    def handle_mention(self, client: WebClient, body: dict):
        logging.debug("handle_mention")
        event = body["event"]
        channel_id = event["channel"]
        user_id = event["user"]
        text = event["text"]
        msg_ts = event["ts"]

        in_thread = "thread_ts" in event
        conversation_id = None

        if in_thread:
            conversation_id = "71a0dc14-c060-49bd-b6f7-0f9bdbcaa8be"
            messages = {"messages": []}
            x = client.conversations_replies(channel=channel_id, ts=event["thread_ts"], include_all_metadata=True)
            time.sleep(2)
            logging.debug(f"Messages: {messages}")

            for message in messages["messages"]:
                if "metadata" not in message:
                    continue

                meta = message["metadata"]
                if meta["event_type"] != "dify_conversation_started" or "event_payload" not in meta:
                    continue

                conversation_id = meta["event_payload"]["dify_conversation_id"]
                break

        try:
            logging.info(f"Starting workflow for {channel_id}, {text}, {conversation_id}")
            answer = self.start_workflow(channel_id, text, conversation_id)
            logging.debug(f"handle_mention:answer: {answer}")
        except ConfigNotFound as e:
            client.chat_postMessage(text=str(e), channel=channel_id, thread_ts=msg_ts)

        if not in_thread and "conversation_id" in answer:
            metadata = {
                "event_type": "dify_conversation_started",
                "event_payload": {
                    "dify_conversation_id": answer["conversation_id"],
                }
            }
        else:
            metadata = None

        logging.debug(f"Posting response {answer['answer']}")
        client.chat_postMessage(text=f"<@{user_id}>, {answer['answer']}", thread_ts=msg_ts, channel=channel_id, metadata=metadata)

    def handle_dm(self, ack: Ack, say: Say, client: WebClient, body: dict):
        if not is_dm(body):
            ack()
            return

        event = body["event"]
        message = event["text"]
        sender_id = event["user"]

        if sender_id not in self._slack_admins:
            say("Not an admin, sorry.")
            return

        if "get config" in message:
            try:
                config = self.session.storage.get("config").decode()
                logging.info(config)
                say(config)
                return
            except Exception as e:
                logging.error(e, exc_info=True)
                say("No config found.")
                return

        elif "set config" in message:
            new_config = message.split("set config ")[1]
            try:
                json.loads(new_config)
                logging.info(new_config)
            except json.JSONDecodeError as e:
                say(f"Invalid JSON, try again.: {e}")
                return

            self.session.storage.set(STORAGE_CONFIG_KEY, new_config.encode("utf-8"))
            say("Config saved!")
            return

    def start_workflow(self, channel_id: str, message: str, conversation_id: str | None = None):        
        conf = None
        if self._slack_config is None:
            raise ConfigNotFound("Bot is unconfigured, or channel -> workflow mapping not found")

        for c in self._slack_config:
            if c["channel_id"] == channel_id:
                conf = c
                break

        if conf is None:
            raise ConfigNotFound("Channel not found in config")

        try:
            if conf["dify_type"] == "chatflow":
                logging.info(f"Workflow: {conf['dify_id']}, msg: {message}, conv_id: {conversation_id}")

                response = self.session.app.chat.invoke(
                    app_id=conf["dify_id"],
                    query=message,
                    inputs={},
                    response_mode="blocking",
                    conversation_id=conversation_id
                )

                logging.debug(f"start_workflow:response: {response}")
                return response
            elif conf["dify_type"] == "workflow":
                # then try to invoke a workflow, this is currently broken since workflows require input
                response = self.session.app.workflow.invoke(
                    app_id=conf["dify_id"],
                    inputs={},
                    response_mode="blocking"
                )

                logging.info(response)
        except Exception as e:
            logging.error(e, stack_info=True)
            return {"answer": f"Exception: {e}"}