import asyncio

from cairo_dap.channel import OutputChannel
from cairo_dap.messaging import Request, read_message


class _MessageDispatcher:
    def __init__(self):
        self._registry = dict()
        self._fallback = None

    def call(self, server, message: Request):
        func = self._registry.get(message.command)
        if func is None:
            return self._fallback(server, message)
        return func(server, message)

    def register(self, message_type):
        def wrapper(func):
            self._registry[message_type] = func
            return func
        return wrapper

    def fallback(self):
        def wrapper(func):
            self._fallback = func
            return func
        return wrapper


class Server:
    dispatcher = _MessageDispatcher()

    def __init__(self, runner, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.runner = runner
        self.reader = reader
        self.output = OutputChannel(writer)

    async def run_forever(self):
        while True:
            message = await read_message(self.reader)
            await self.dispatcher.call(self, message)

    @dispatcher.register('initialize')
    async def on_initialize(self, request):
        await self.output.send_response(request, self._capabilities())
        await self.output.send_event('initialized', {})

    @dispatcher.register('disconnect')
    async def on_attach(self, request):
        await self.output.send_response(request, {})

    @dispatcher.register('attach')
    async def on_attach(self, request):
        await self.output.send_response(request, {})

        await self.output.send_event('process', {
            'name': 'foobar',
            'startMethod': 'attach'
        })
        await self.output.send_event('stopped', {
            'reason': 'entry',
            'allThreadsStopped': True,
        })

    @dispatcher.register('configurationDone')
    async def on_configuration_done(self, request):
        await self.output.send_response(request, {})
        await self.output.send_event('stopped', {
            'reason': 'entry',
            'threadId': 0,
        })

    @dispatcher.register('pause')
    async def on_pause(self, request):
        await self.output.send_response(request, {})

    @dispatcher.register('continue')
    async def on_pause(self, request):
        await self.output.send_response(request, {})

        self.runner.continue_until_breakpoint()
        await self.output.send_event('stopped', {
            'reason': 'breakpoint',
            'threadId': 0,
            'allThreadsStopped': True
        })
        await self._check_if_exited()

    @dispatcher.register('next')
    async def on_pause(self, request):
        await self.output.send_response(request, {})

        self.runner.step()
        await self.output.send_event('stopped', {
            'reason': 'step',
            'threadId': 0,
            'allThreadsStopped': True
        })
        await self._check_if_exited()

    @dispatcher.register('setFunctionBreakpoints')
    async def on_set_function_breakpoints(self, request):
        breakpoints = [
            self.runner.add_function_breakpoint(breakpoint)
            for breakpoint in request.arguments['breakpoints']
            if breakpoint is not None
        ]

        await self.output.send_response(request, {'breakpoints': breakpoints})

    @dispatcher.register('breakpointLocations')
    async def on_set_function_breakpoints(self, request):
        await self.output.send_response(request, {'breakpoints': []})

    @dispatcher.register('threads')
    async def on_threads(self, request):
        threads = [{'id': 0, 'name': 'main'}]
        await self.output.send_response(request, {'threads': threads})

    @dispatcher.register('stackTrace')
    async def on_stack_trace(self, request):
        args = request.arguments
        stack_frames, total_frames = self.runner.stack_trace(args['startFrame'], args['levels'])
        await self.output.send_response(request, {'stackFrames': stack_frames, 'totalFrames': total_frames})

    @dispatcher.register('scopes')
    async def on_scopes(self, request):
        frame_id = request.arguments['frameId']
        scopes = self.runner.scopes(frame_id)
        await self.output.send_response(request, {'scopes': scopes})

    @dispatcher.register('variables')
    async def on_variables(self, request):
        variables_ref = request.arguments['variablesReference']
        variables = self.runner.variables(variables_ref)
        await self.output.send_response(request, {'variables': variables})

    @dispatcher.fallback()
    async def unhandled_request(self, message):
        print('Unhandled', message)

    def _capabilities(self):
        return {
            'supportsConfigurationDoneRequest': True,
            'supportsFunctionBreakpoints': True,
            'supportsBreakpointLocationsRequest': True,
            'supportsStepBack': False,
            'supportsRestartRequest': False,
            'supportsReadMemoryRequest': True,
        }

    async def _check_if_exited(self):
        if self.runner.has_exited():
            await self.output.send_event('exited', {
                'exitCode': 0,
            })
            await self.output.send_event('terminated', {
                'restart': False,
            })


async def dap_server(runner, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    server = Server(runner, reader, writer)
    await server.run_forever()


def dap_server_wrapper(runner):
    # Huge hack while we properly start programs from inside the server.
    async def func(reader, writer):
        await dap_server(runner, reader, writer)
    return func


async def serve(runner, host='localhost', port=0):
    server = await asyncio.start_server(dap_server_wrapper(runner), host, port)

    addr = server.sockets[0].getsockname()
    print(f'Serving on {addr}')

    async with server:
        await server.serve_forever()
