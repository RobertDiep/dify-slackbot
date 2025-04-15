from .slackrequesthandler import SlackRequestHandler


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
