import time
import logging
import json
from typing import Mapping
from werkzeug import Request, Response
from dify_plugin import Endpoint
from dify_plugin.config.logger_format import plugin_logger_handler

from slack_bolt import App

from slack_bolt.request import BoltRequest
from slack_bolt.response import BoltResponse


logger = logging.getLogger()
logger.setLevel(logging.INFO)

class ConfigNotFound(Exception):
    pass

class ConfigIncorrect(Exception):
    pass

def to_bolt_request(req: Request) -> BoltRequest:
    data = req.get_data(as_text=True)
    logger.info(data)
    return BoltRequest(
        body=data,
        query=req.query_string.decode('utf-8'),
        headers=req.headers
    )


def to_werkzeug_response(bolt_resp: BoltResponse) -> Response:
    resp: Response = Response(bolt_resp.body, bolt_resp.status)
    for k, values in bolt_resp.headers.items():
        if k.lower() == "content-type" and resp.headers.get("content-type") is not None:
            # Remove the one set by Flask
            resp.headers.pop("content-type")
        for v in values:
            resp.headers.add_header(k, v)
    return resp

def is_dm(body):
    authorization_id = body["authorizations"][0]["user_id"]
    event_rcv_id = body["event"]["parent_user_id"]

    return authorization_id == event_rcv_id

def make_plaintext_block(text):
    return {
        "type": "section",
        "text": {
            "type": "plain_text",
            "text": text,
            "emoji": True
        }
    }

def make_plaintext_input_block(name, description, multiline=True):
    block = {
        "type": "input",
        "element": {
            "type": "plain_text_input",
            "multiline": multiline,
            "action_id": name,
        },
        "label": {
            "type": "plain_text",
            "text": description,
            "emoji": True
        }
    }
    return block

def make_url_block(name, description):
    block = {
        "type": "input",
        "element": {
            "type": "url_text_input",
            "action_id": name,
        },
        "label": {
            "type": "plain_text",
            "text": description,
            "emoji": True
        }
    }
    return block

def params_to_modal(config):
    divider = {"type": "divider"}

    blocks = {
        "type": "modal",
        "callback_id": config["dify_id"],
        "title": {"type": "plain_text", "text": config["title"], "emoji": False},
        "submit": {"type": "plain_text", "text": "Submit", "emoji": False},
        "clear_on_close": True,
        "close": {"type": "plain_text", "text": "Cancel", "emoji": True},
        "blocks": [divider, make_plaintext_block(config["description"]), divider]
    }
    for param in config["parameters"]:
        type_ = param["type"]
        block = {}
        if type_ == "plain_text":
            block = make_plaintext_input_block(param["name"], param["description"])
        elif type_ == "url_text_input":
            pass
        else:
            raise ConfigIncorrect(f"Parameter type {type_} not implemented")

        blocks["blocks"].append(block)

    return blocks

class SlackRequestHandler:
    def __init__(self, app: App):
        self.app = app

    def handle(self, req: Request) -> Response:
        if req.method == "GET":
            # oauth flow is not implemented yet
            pass
        elif req.method == "POST":
            bolt_resp = self.app.dispatch(to_bolt_request(req))
            return to_werkzeug_response(bolt_resp)
        return Response("Not found", 404)


class NwSlackbotEndpoint(Endpoint):

    def _invoke(self, r: Request, values: Mapping, settings: Mapping) -> Response:
        """
        Invokes the endpoint with the given request.
        """

        # try to get config from storage
        try:
            config = self.session.storage.get("config")
            self._slack_config = json.loads(config)
        except json.JSONDecodeError:
            config = None
            self._slack_config = None

        slack_app = App(token=settings.get("bot_token"), signing_secret=settings.get("signing_secret"))

        @slack_app.event("app_mention")
        def mention(body, say, logger):
            event = body["event"]
            channel_id = event["channel"]
            user_id = event["user"]
            text = event["text"]
            msg_ts = event["ts"]

            try:
                answer = self.start_workflow(channel_id, text)
            except ConfigNotFound:
                return say("No workflow associated with this channel.")

            say(f"<@{user_id}>, {answer}", thread_ts=msg_ts)

        @slack_app.event("message")
        def msg(body, ack, say):
            if not is_dm(body):
                return ack()

            event = body["event"]
            message = event["text"]
            sender_id = event["user"]
            admins = settings.get("slack_admin_ids").split(",")

            if sender_id not in admins:
                return say("Not an admin, sorry.")

            if "get config" in message:
                try:
                    config = self.session.storage.get("config").decode()
                    logger.info(config)
                    return say(config)
                except Exception as e:
                    logger.error(e, exc_info=True)
                    return say("No config found.")

            elif "set config" in message:
                new_config = message.split("set config ")[1]
                try:
                    json.loads(new_config)
                except json.JSONDecodeError:
                    return say("Invalid JSON, try again.")

                self.session.storage.set("config", new_config.encode("utf-8"))
                return say("Config saved!")

        handler = SlackRequestHandler(slack_app)

        return handler.handle(r)

    def start_workflow(self, channel_id: str, message: str):
        conf = None

        if self._slack_config is None:
            return "Bot is unconfigured, notify an admin."

        for c in self._slack_config:
            if c['channel_id'].lower() == channel_id.lower():
                conf = c

        if conf is None:
            raise ConfigNotFound("Channel -> workflow ID mapping not found")

        try:
            if c["dify_type"] == "chatflow":
                # first try to invoke a chatflow/chatapp
                response = self.session.app.chat.invoke(
                    app_id=conf["dify_id"],
                    query=message,
                    inputs={},
                    response_mode="blocking"
                )

                logger.info(response)

                return response.get("answer")
            elif c["dify_type"] == "workflow":
                # then try to invoke a workflow, this is currently broken since workflows require input
                response = self.session.app.workflow.invoke(
                    app_id=conf["dify_id"],
                    inputs={},
                    response_mode="blocking"
                )

                logger.info(response)

                return response.get('answer')
        except Exception as e:
            return f"Exception: {e}"
