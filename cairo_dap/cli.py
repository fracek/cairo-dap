"""
Cairo DAP cli entrypoint.
"""
import argparse
import asyncio
import logging
import json
import sys
import tempfile

from starkware.cairo.lang.tracer.tracer_data import TracerData
from starkware.cairo.lang.instances import LAYOUTS
from starkware.cairo.lang.compiler.program import Program, ProgramBase
from starkware.cairo.lang.vm.cairo_runner import CairoRunner
from starkware.cairo.lang.vm.memory_dict import MemoryDict

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
    initial_memory = MemoryDict()

    runner = CairoRunner(program=program, layout=args.layout, memory=initial_memory, proof_mode=False)

    runner.initialize_segments()
    end = runner.initialize_main_entrypoint()

    program_input = json.load(args.program_input) if args.program_input else {}
    runner.initialize_vm(hint_locals={'program_input': program_input})

    await serve(port=9999)


def _load_program(program):
    program_json = json.load(program)
    return Program.Schema().load(program_json)