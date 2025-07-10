import logging
import json
import threading
import re

from dify_plugin import Endpoint
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from slack_sdk.errors import SlackApiError
from collections.abc import Mapping
from werkzeug import Request, Response

from .utils import is_dm, is_self_event


class ConfigNotFound(Exception):
    pass


STORAGE_CONFIG_KEY = "config"

logger = logging.getLogger(__name__)


class NwSlackEndpoint(Endpoint):
    def __init__(self, session):
        super().__init__(session)
        self.lock = threading.Lock()

    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        logger.info(r)
        # set slack admins
        self._slack_admins = settings.get("slack_admin_ids").split(",")

        # try to get config from settings
        try:
            logger.debug(settings.get("channel_config", "[]"))
            self._slack_config = json.loads(settings.get("channel_config", "[]"))
        except Exception as e:
            logger.exception(e)
            self._slack_config = None
        #
        # Slack stuff
        #

        # if retry due to a HTTP timeout, the workflow might be too long so return 200 OK
        retry_num = r.headers.get("X-Slack-Retry-Num")
        if r.headers.get("X-Slack-Retry-Reason") == "http_timeout" and (
            retry_num is not None and int(retry_num) > 0
        ):
            return Response(status=200, response="ok")

        # Verify request
        verifier = SignatureVerifier(signing_secret=settings.get("signing_secret"))
        signature = r.headers.get("X-Slack-Signature")
        timestamp = r.headers.get("X-Slack-Request-Timestamp")

        if not verifier.is_valid(r.get_data(), timestamp, signature):
            logger.error("Invalid signature for Slack request")
            return Response(status=200, response="ok")

        # handle data
        webclient = WebClient(token=settings.get("bot_token"))
        data = r.get_json()
        req_type = data.get("type")
        if req_type == "url_verification":
            return Response(
                response=json.dumps({"challenge": data.get("challenge")}),
                status=200,
                content_type="application/json",
            )

        elif req_type == "event_callback":
            event = data.get("event")
            event_type = event.get("type")

            try:
                match event_type:
                    case "app_mention":
                        self.handle_mention(body=data, client=webclient)
                    case "message":
                        self._save_message(data)
                        self.handle_dm(body=data, client=webclient)
            except SlackApiError as e:
                logger.exception(e)
            finally:
                return Response(status=200, response="ok")

    def handle_mention(self, client: WebClient, body: dict):
        logger.debug("begin")

        event = body["event"]
        channel_id = event["channel"]
        user_id = event["user"]
        text = re.sub(r"^<@[^>]+>\s*", "", event["text"])
        msg_ts = event["ts"]

        in_thread = "thread_ts" in event
        thread_ts = event["thread_ts"] if in_thread else msg_ts

        conversation_id = self._get_conversation_id(channel_id, thread_ts)
        try:
            logger.info(
                f"Starting workflow for {channel_id}, {text}, {conversation_id}"
            )
            answer = self.start_workflow(channel_id, text, conversation_id)
            logger.debug(f"handle_mention:answer: {answer}")
        except ConfigNotFound as e:
            client.chat_postMessage(text=str(e), channel=channel_id, thread_ts=msg_ts)

        # set conversation id on new message
        if "conversation_id" in answer:
            logger.debug("Saving conversation id")
            self._save_conversation_id(channel_id, thread_ts, answer["conversation_id"])

            # Despite not using the conversation_id from Slack's metadata
            # we still want to include it to the server.
            metadata = {
                "event_type": "dify_conversation_started",
                "event_payload": {
                    "dify_conversation_id": answer["conversation_id"],
                },
            }
        else:
            metadata = None

        logger.debug(f"Posting response {answer['answer']}")

        client.chat_postMessage(
            text=f"<@{user_id}>, {answer['answer']}",
            thread_ts=msg_ts,
            channel=channel_id,
            metadata=metadata,
        )

    def handle_dm(self, client: WebClient, body: dict):
        if is_self_event(body):
            logger.debug("Self event, return")
            return

        if not is_dm(body):
            return

        event = body["event"]
        message = event["text"]
        sender_id = event["user"]
        receiver = sender_id
        thread_ts = event["thread_ts"] if "thread_ts" in event else event["ts"]

        if sender_id not in self._slack_admins:
            # client.chat_postMessage(channel=receiver, text="Not an admin, sorry.")
            return

        if "get config" in message:
            try:
                config = self.session.storage.get("config").decode()
                logger.info(config)
                client.chat_postMessage(
                    channel=receiver, thread_ts=thread_ts, text=config
                )
                return
            except Exception as e:
                logger.error(e, exc_info=True)
                client.chat_postMessage(
                    channel=receiver, thread_ts=thread_ts, text="No config found."
                )
                return

    def start_workflow(
        self, channel_id: str, message: str, conversation_id: str | None = None
    ):
        conf = None
        for c in self._slack_config:
            if c["channel_id"] == channel_id:
                conf = c
                break

        if conf is None:
            raise ConfigNotFound("Channel not found in config")

        try:
            if conf["dify_type"] == "chatflow":
                logger.info(
                    f"Workflow: {conf['dify_id']}, msg: {message}, conv_id: {conversation_id}"
                )

                response = self.session.app.chat.invoke(
                    app_id=conf["dify_id"],
                    query=message,
                    inputs={},
                    response_mode="blocking",
                    conversation_id=conversation_id,
                )

                logger.debug(f"start_workflow:response: {response}")
                return response
            elif conf["dify_type"] == "workflow":
                # then try to invoke a workflow, this is currently broken since workflows require input
                response = self.session.app.workflow.invoke(
                    app_id=conf["dify_id"], inputs={}, response_mode="blocking"
                )

                logger.info(response)
        except Exception as e:
            logger.error(e, stack_info=True)
            return {"answer": f"Exception: {e}"}

    def _get_conversation_id(self, channel_id: str, thread_ts: str):
        key = channel_id + "-" + thread_ts
        try:
            if self.session.storage.exist(key):
                stored_data = self.session.storage.get(key)
                conversation_id = stored_data.decode("utf-8")
                logger.debug(f"Got conv_id: f{conversation_id[:8]}")

                return conversation_id
            else:
                logger.debug(f"No conversation id for {thread_ts}")
                return None
        except Exception as e:
            logger.warning(f"Get conv id warning: {str(e)}")
            return None

    def _save_conversation_id(
        self, channel_id: str, thread_ts: str, conversation_id: str
    ):
        key = channel_id + "-" + thread_ts
        try:
            if self.session.storage.exist(key):
                return
            self.session.storage.set(key, conversation_id.encode("utf-8"))
            logger.info(f"Set conv id {conversation_id[:8]} for thread {thread_ts}")
        except Exception as e:
            logger.exception("Error in conversation ID", e)

    def _save_message(self, message):
        key = "debuglog"

        if self.session.storage.exist(key):
            data = json.loads(self.session.storage.get(key).decode("utf-8"))
            data.append(message)
            self.session.storage.set(key, json.dumps(data).encode(("utf-8")))
        else:
            self.session.storage.set(key, json.dumps([message]).encode("utf-8"))
