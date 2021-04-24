"""
Cairo DAP cli entrypoint.
"""
import argparse
import asyncio
import json
import logging
import sys
import tempfile

from starkware.cairo.lang.compiler.program import Program
from starkware.cairo.lang.instances import LAYOUTS

from cairo_dap.runner import Runner
from cairo_dap.server import serve


def main():
    """Parse command line arguments and start the server."""
    args = argparse.ArgumentParser(
        description='Debug Adapter Protocol server for the Cairo language')

    args.add_argument(
        '--program', type=argparse.FileType('r'), help='The name of the program json file.')
    args.add_argument(
        '--program_input', type=argparse.FileType('r'),
        help='Path to a json file representing the (private) input of the program.')
    args.add_argument(
        '--memory_file', type=argparse.FileType('wb'), help='Output file name for the memory.')
    args.add_argument(
        '--trace_file', type=argparse.FileType('wb'), help='Output file name for the execution trace.')
    args.add_argument(
        '--debug_info_file', type=argparse.FileType('w'),
        help='Output file name for debug information created at run time.')
    args.add_argument(
        '--layout', choices=LAYOUTS.keys(), default='plain',
        help='The layout of the Cairo AIR.')
    args = args.parse_args(sys.argv[1:])

    logging.basicConfig()
    logging.getLogger().setLevel(logging.DEBUG)
    asyncio.run(cairo_dap(args))


async def cairo_dap(args):
    """Start the DAP server."""
    trace_file = args.trace_file
    if trace_file is None:
        trace_file = tempfile.NamedTemporaryFile(mode='wb')

    memory_file = args.memory_file
    if memory_file is None:
        memory_file = tempfile.NamedTemporaryFile(mode='wb')

    debug_info_file = args.debug_info_file
    if debug_info_file is None:
        debug_info_file = tempfile.NamedTemporaryFile(mode='w')

    program = _load_program(args.program)
    program_input = json.load(args.program_input) if args.program_input else {}

    runner = Runner(program, program_input, args.layout)

    await serve(runner, port=9999)


def _load_program(program):
    program_json = json.load(program)
    return Program.Schema().load(program_json)