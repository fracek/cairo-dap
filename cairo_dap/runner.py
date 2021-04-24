import logging
from pathlib import Path

from starkware.cairo.lang.compiler.identifier_manager import MissingIdentifierError
from starkware.cairo.lang.vm.cairo_runner import CairoRunner
from starkware.cairo.lang.vm.memory_dict import MemoryDict
from starkware.cairo.lang.compiler.expression_evaluator import ExpressionEvaluator
from starkware.cairo.lang.compiler.substitute_identifiers import substitute_identifiers
from starkware.cairo.lang.compiler.type_system_visitor import simplify_type_system
from starkware.cairo.lang.compiler.parser import parse_expr
from starkware.cairo.lang.compiler.identifier_definition import ConstDefinition, ReferenceDefinition
from starkware.cairo.lang.compiler.identifier_utils import resolve_search_result
from starkware.cairo.lang.compiler.offset_reference import OffsetReferenceDefinition
from starkware.cairo.lang.compiler.scoped_name import ScopedName
from starkware.cairo.lang.compiler.ast.expr import ExprConst, ExprIdentifier
from starkware.cairo.lang.compiler.references import FlowTrackingError, SubstituteRegisterTransformer
from starkware.cairo.lang.compiler.ast.cairo_types import TypeStruct

_logger = logging.getLogger(__name__)


class Runner:
    def __init__(self, program, program_input, layout):
        initial_memory = MemoryDict()

        runner = CairoRunner(program=program, layout=layout, memory=initial_memory, proof_mode=False)

        runner.initialize_segments()
        runner.initialize_main_entrypoint()
        runner.initialize_vm(hint_locals={'program_input': program_input})

        self._runner = runner

        self._runner.vm.get_traceback()

        self._breakpoints = []
        self._frame_data = FrameData()

    def add_function_breakpoint(self, breakpoint):
        func_name = breakpoint['name']
        try:
            pc = self._runner.program.get_label(func_name)
            _logger.info('Added breakpoint: %s %d', func_name, pc)
        except MissingIdentifierError:
            _logger.info('Breakpoint not found: %s', func_name)
            return None

        breakpoint = {
            'id': breakpoint['id'],
            'pc': pc
        }

        self._breakpoints.append(breakpoint)

        return {
            'id': breakpoint['id'],
            'verified': True,
        }

    def stack_trace(self, start_frame, levels):
        frames = self._frame_data.frames

        filtered_frames = [
            frame for i, frame in enumerate(frames)
            if start_frame <= i < start_frame + levels
        ]

        return filtered_frames, len(frames)

    def scopes(self, frame_id):
        return self._frame_data.scopes_by_frame[frame_id]

    def variables(self, variables_ref):
        return self._frame_data.variables_by_reference[variables_ref]

    def step(self):
        self._runner.vm_step()
        self._compute_frame_data()

    def has_exited(self):
        return self._runner.vm.run_context.pc == self._runner.final_pc

    def continue_until_breakpoint(self):
        runner = self._runner
        while True:
            breakpoint_hit = False
            for breakpoint in self._breakpoints:
                if runner.vm.run_context.pc == breakpoint['pc']:
                    breakpoint_hit = True
                    break

            if breakpoint_hit:
                break

            if runner.vm.run_context.pc == runner.final_pc:
                break

            runner.vm_step()

        self._compute_frame_data()

    def _compute_frame_data(self):
        # Compute stack frame data.
        # At each location we have the stack frame (current location + call stack),
        # each frame has several variables scope (locals + globals), each scope has
        # a collection of variables.
        #
        # The client will ask for this data in separate requests, but we compute
        # everything in this function.

        frame_data = FrameData()
        cwd = Path.cwd()
        runner = self._runner

        frame, scopes_with_variables = _frame_data_at_pc(cwd, runner, runner.vm.run_context.pc)
        frame_data.add_frame_data(frame, scopes_with_variables)

        for traceback_pc in reversed(runner.vm.run_context.get_traceback_entries()):
            frame, scopes_with_variables = _frame_data_at_pc(cwd, runner, traceback_pc)
            frame_data.add_frame_data(frame, scopes_with_variables)

        self._frame_data = frame_data


class FrameData:
    def __init__(self):
        self.frames = []
        self.scopes_by_frame = dict()
        self.variables_by_reference = dict()

        self._var_ref_id = 1

    def add_frame_data(self, frame, scopes_with_variables):
        id = len(self.frames)
        frame['id'] = id
        self.frames.append(frame)
        for scope in scopes_with_variables:
            ref = self._next_variable_reference()
            self.variables_by_reference[ref] = scope['variables']
            scope['variablesReference'] = ref
            del scope['variables']
        self.scopes_by_frame[id] = scopes_with_variables

    def _next_variable_reference(self):
        v = self._var_ref_id
        self._var_ref_id += 1
        return v


def _frame_data_at_pc(cwd, runner, pc):
    frame = _frame_at_pc(cwd, runner, pc)
    variables = _variables_at_pc(runner, pc)
    scopes = [{
        'name': 'Locals',
        'presentationHint': 'locals',
        'variablesReference': None,
        'namedVariables': len(variables),
        'expensive': False,
        'variables': variables,
    }]
    return frame, scopes


def _frame_at_pc(cwd, runner, pc):
    location = runner.vm.get_location(pc=pc)
    return {
        'source': {
            'path': str(cwd / location.inst.input_file.filename)
        },
        'line': location.inst.start_line,
        'endLine': location.inst.end_line,
        'column': location.inst.start_col,
        'endColumn': location.inst.end_col,
    }


def _variables_at_pc(runner, pc):
    # TODO: what's the implication of not relocating?
    pc_offset = pc - runner.program_base
    scope_name = runner.program.debug_info.instruction_locations[pc_offset].accessible_scopes[-1]
    scope_items = runner.program.identifiers.get_scope(scope_name).identifiers

    variables = []
    watch_evaluator = WatchEvaluator(runner.program, runner.vm.run_context, runner.program_base)

    for name, identifier_definition in scope_items.items():
        if isinstance(identifier_definition, ReferenceDefinition):
            value = watch_evaluator.eval(name)
            variables.append({
                'name': name,
                'value': value,
                'variablesReference': 0,
            })
    return variables


class WatchEvaluator(ExpressionEvaluator):
    def __init__(self, program, run_context, program_base):
        super().__init__(program.prime, ap=run_context.ap, fp=run_context.fp, memory=run_context.memory)

        self.program = program
        self.pc = run_context.pc
        self.ap = run_context.ap
        self.fp = run_context.fp
        self.program_base = program_base

        pc_offset = self.pc - program_base
        self.accessible_scopes = program.debug_info.instruction_locations[pc_offset].accessible_scopes

    def eval(self, expr):
        if expr == 'null':
            return ''
        return 'TODO'
