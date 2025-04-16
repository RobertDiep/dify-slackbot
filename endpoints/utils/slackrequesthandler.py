from werkzeug import Request, Response
from slack_bolt import App
from slack_bolt.request import BoltRequest
from slack_bolt.response import BoltResponse
from slack_bolt.lazy_listener import ThreadLazyListenerRunner
from concurrent.futures import ThreadPoolExecutor
from slack_bolt.logger import get_bolt_app_logger


def to_bolt_request(req: Request) -> BoltRequest:
    data = req.get_data(as_text=True)
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


class SlackRequestHandler:
    def __init__(self, app: App, threadpoolexecutor: bool = False):
        self.app = app
        self.logger = get_bolt_app_logger(app.name, SlackRequestHandler, app.logger)
        self._executor = ThreadPoolExecutor(max_workers=3)

        if threadpoolexecutor:
            self.app.listener_runner.lazy_listener_runner = ThreadLazyListenerRunner(self.logger, self._executor)

    def handle(self, req: Request) -> Response:
        if req.method == "GET":
            # oauth flow is not implemented yet
            pass
        elif req.method == "POST":
            bolt_resp = self.app.dispatch(to_bolt_request(req))
            return to_werkzeug_response(bolt_resp)
        return Response("Not found", 404)
