import asyncio
import json

from cairo_dap.messaging import Request, Response, Event, read_message, write_message


async def dap_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    # Initialize
    message = await read_message(reader)
    response = Response(1, message.seq, True, 'initialize', None, {})
    await write_message(writer, response)

    # Attach
    message = await read_message(reader)
    response = Response(2, message.seq, True, 'attach', None, None)
    await write_message(writer, response)

    # Initialized
    event = Event(3, 'initialized', None)
    await write_message(writer, event)

    event = Event(4, 'continued', {'threadId': 1})
    await write_message(writer, event)

    # Set exception breakpoints
    #message = await read_message(reader)
    #response = Response(4, message.seq, True, 'setExceptionBreakpoints', None, None)
    #await write_message(writer, response)

    # Threads
    #message = await read_message(reader)
    #print(message)
    #response = Response(5, message.seq, True, 'threads', None, {'threads': [{'id': 1, 'name': 'main'}]})
    #await write_message(writer, response)

    # Configuration done
    #message = await read_message(reader)
    #response = Response(4, message.seq, True, 'configurationDone', None, None)
    #await write_message(writer, response)

    while True:
        message = await read_message(reader)
        print(message)



async def serve(host='localhost', port=0):
    server = await asyncio.start_server(dap_server, host, port)

    addr = server.sockets[0].getsockname()
    print(f'Serving on {addr}')

    async with server:
        await server.serve_forever()