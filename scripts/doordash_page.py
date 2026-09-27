"""Read public DoorDash server-rendered records without executing page JavaScript."""
import json
import re


def records(value, depth=0):
    if depth > 80:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from records(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            yield from records(child, depth + 1)
    elif isinstance(value, str) and value.startswith(('{', '[')):
        try:
            decoded = json.loads(value)
        except ValueError:
            return
        yield from records(decoded, depth + 1)


def store_header(body, store_id):
    chunks = []
    for match in re.finditer(r'self\.__next_f\.push\((\[.*?\])\)', body.decode('utf-8'), re.S):
        try:
            chunk = json.loads(match[1])
        except ValueError:
            continue
        if len(chunk) > 1 and isinstance(chunk[1], str):
            chunks.append(chunk[1])
    for line in ''.join(chunks).splitlines():
        payload = line.partition(':')[2]
        if not payload.startswith(('{', '[', '"')):
            continue
        try:
            root = json.loads(payload)
        except ValueError:
            continue
        for record in records(root):
            header = record.get('storeHeaderLite')
            if isinstance(header, dict) and str(header.get('id')) == store_id:
                return header
    return None
