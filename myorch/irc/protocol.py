import secrets

from myorch.irc.messages import Message


def new_batch_id() -> str:
    return secrets.token_hex(6)


def encode_batch(
    batch_id: str,
    type_: str,
    tags: dict[str, str],
    target: str,
    contents: list[str],
) -> list[str]:
    if not contents:
        raise ValueError("encode_batch requires at least one content line")

    open_msg = Message(
        command="BATCH",
        params=[f"+{batch_id}", type_, target],
        tags=dict(tags),
    )
    body = [
        Message(
            command="PRIVMSG",
            params=[target, line],
            tags={"batch": batch_id},
        )
        for line in contents
    ]
    close_msg = Message(command="BATCH", params=[f"-{batch_id}"])
    return [open_msg.encode(), *(b.encode() for b in body), close_msg.encode()]


def encode_multiline(
    target: str,
    content: str,
    tags: dict[str, str],
) -> list[str]:
    if "\n" not in content:
        return [
            Message(
                command="PRIVMSG",
                params=[target, content],
                tags=dict(tags),
            ).encode()
        ]
    return encode_batch(
        batch_id=new_batch_id(),
        type_="draft/multiline",
        tags=tags,
        target=target,
        contents=content.split("\n"),
    )
