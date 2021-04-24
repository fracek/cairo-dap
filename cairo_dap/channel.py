import asyncio

from cairo_dap.messaging import Event, Request, Response, write_message


class OutputChannel:
    def __init__(self, writer: asyncio.StreamWriter):
        self.seq = 1
        self._seq_lock = asyncio.Lock()
        self.writer = writer

    async def send_event(self, event_name, body):
        seq = await self._get_and_inc_seq()
        event = Event(seq, event_name, body)
        await write_message(self.writer, event)

    async def send_response(self, request: Request, body):
        seq = await self._get_and_inc_seq()
        response = Response(seq, request.seq, True, request.command, None, body)
        await write_message(self.writer, response)

    async def send_error_response(self, request: Request, message, format, variables):
        seq = await self._get_and_inc_seq()
        body = {
            'error': {
                'id': seq,
                'format': format,
                'variables': variables,
            }
        }
        response = Response(seq, request.seq, False, request.command, message, body)
        await write_message(self.writer, response)

    async def _get_and_inc_seq(self):
        async with self._seq_lock:
            seq = self.seq
            self.seq += 1
            return seq
