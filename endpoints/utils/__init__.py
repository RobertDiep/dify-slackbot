def is_dm(body):
    return body["event"]["channel_type"] == "im"


def is_self_event(body):
    event = body["event"]
    bot_ids = [x["user_id"] for x in body["authorizations"]]
    user_id = event["user"]

    return user_id in bot_ids


def make_plaintext_block(text):
    return {
        "type": "section",
        "text": {"type": "plain_text", "text": text, "emoji": True},
    }


def make_plaintext_input_block(name, description, multiline=True):
    block = {
        "type": "input",
        "element": {
            "type": "plain_text_input",
            "multiline": multiline,
            "action_id": name,
        },
        "label": {"type": "plain_text", "text": description, "emoji": True},
    }
    return block


def make_url_block(name, description):
    block = {
        "type": "input",
        "element": {
            "type": "url_text_input",
            "action_id": name,
        },
        "label": {"type": "plain_text", "text": description, "emoji": True},
    }
    return block
