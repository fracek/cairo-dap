import asyncio
import json
import logging


_logger = logging.getLogger(__name__)


class Message:
    def __init__(self, seq):
        self.seq = seq

    def to_dict(self):
        raise NotImplementedError


class Event(Message):
    def __init__(self, seq, event, body):
        super().__init__(seq)
        self.event = event
        self.body = body

    @staticmethod
    def parse(json):
        seq = json['seq']
        event = json['event']
        body = json.get('body')
        return Event(seq, event, body)

    def to_dict(self):
        return {
            'seq': self.seq,
            'type': 'event',
            'event': self.event,
            'body': self.body
        }

    def __str__(self):
        return 'Event(seq={}, event={}, body={})'.format(self.seq, self.event, self.body)


class Request(Message):
    def __init__(self, seq, command, arguments):
        super().__init__(seq)
        self.command = command
        self.arguments = arguments

    @staticmethod
    def parse(json):
        seq = json['seq']
        command = json['command']
        arguments = json.get('arguments')
        return Request(seq, command, arguments)

    def to_dict(self):
        return {
            'seq': self.seq,
            'type': 'request',
            'command': self.command,
            'arguments': self.arguments
        }

    def __str__(self):
        return 'Request(seq={}, command={}, arguments={})'.format(self.seq, self.command, self.arguments)


class Response(Message):
    def __init__(self, seq, request_seq, success, command, message, body):
        super().__init__(seq)
        self.request_seq = request_seq
        self.success = success
        self.command = command
        self.message = message
        self.body = body

    @staticmethod
    def parse(json):
        seq = json['seq']
        request_seq = json['request_seq']
        success = json['success']
        command = json['command']
        message = json.get('message')
        body = json.get('body')
        return Response(seq, request_seq, success, command, message, body)

    def to_dict(self):
        return {
            'seq': self.seq,
            'type': 'response',
            'request_seq': self.request_seq,
            'success': self.success,
            'command': self.command,
            'message': self.message,
            'body': self.body
        }

    def __str__(self):
        return 'Request(seq={}, request_seq={}, success={}, command={}, message={}, body={})'.format(
            self.seq, self.request_seq, self.success, self.command, self.message, self.body
        )


_message_parsers = {
    'request': Request.parse,
    'response': Response.parse,
    'event': Event.parse
}


async def read_message(reader: asyncio.StreamReader):
    headers = await _read_headers(reader)

    try:
        length = int(headers[b'Content-Length'])
    except (KeyError, ValueError):
        raise RuntimeError('Content-Length header is missing or invalid')
    body_bytes = await reader.readexactly(length)
    body = json.loads(body_bytes)

    _logger.debug('<<< %s', body_bytes)

    body_type = body['type']
    if body_type not in _message_parsers:
        raise RuntimeError('Invalid message type: {}'.format(body_type))

    parser = _message_parsers[body_type]
    return parser(body)


async def write_message(writer: asyncio.StreamWriter, message: Message):
    body = json.dumps(message.to_dict()).encode('utf8')
    _logger.debug('>>> %s', body)
    body_length = len(body)
    writer.write(b'Content-Length: ')
    writer.write(str(body_length).encode('utf8'))
    writer.write(b'\r\n\r\n')
    writer.write(body)


async def _read_headers(reader):
    headers = dict()

    while True:
        line = await reader.readline()
        if line == b'\r\n':
            break
        key, value = line.strip().split(b':')
        headers[key] = value

    return headers
