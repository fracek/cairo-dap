import logging
from pathlib import Path

from starkware.cairo.lang.compiler.identifier_definition import ReferenceDefinition
from starkware.cairo.lang.compiler.identifier_manager import MissingIdentifierError
from starkware.cairo.lang.compiler.expression_simplifier import to_field_element
from starkware.cairo.lang.vm.cairo_runner import CairoRunner
from starkware.cairo.lang.vm.memory_dict import MemoryDict

from cairo_dap.watch_evaluator import WatchEvaluator

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

        self._function_breakpoints = []
        self._source_breakpoints = dict()
        self._frame_data = FrameData()

        self._has_relocated = False

        self._cwd = Path.cwd()

    def add_function_breakpoint(self, breakpoint):
        func_name = breakpoint['name']
        try:
            offset = self._runner.program.get_label(func_name)
            pc = self._runner.program_base + offset
            _logger.info('Added breakpoint: %s %s', func_name, pc)
        except MissingIdentifierError:
            _logger.info('Breakpoint not found: %s', func_name)
            return {
                'id': breakpoint['id'],
                'verified': False,
            }

        new_breakpoint = self._create_breakpoint_at_pc(pc)
        new_breakpoint['id'] = breakpoint['id']

        self._function_breakpoints.append(new_breakpoint)

        return _breakpoint_json_data(new_breakpoint)

    def add_source_breakpoints(self, source, breakpoints):
        new_breakpoints = []
        path = source['path']

        locations_in_file = []
        for instruction, location in self._runner.vm.instruction_debug_info.items():
            location_path = str(self._cwd / location.inst.input_file.filename)
            if location_path == path:
                locations_in_file.append((location, instruction))

        for breakpoint in breakpoints:
            line = breakpoint['line']
            prev_line = None
            for location, pc in locations_in_file:
                start_line = location.inst.start_line
                end_line = location.inst.end_line

                if start_line <= line <= end_line:
                    _logger.debug('Adding source breakpoint at %s', pc)
                    new_breakpoint = self._create_breakpoint_at_pc(pc)
                    new_breakpoints.append(new_breakpoint)
                elif prev_line is None:
                    pass
                elif prev_line < line <= end_line:
                    # If the user clicked on a comment or empty line,
                    # add breakpoint to the next instruction.
                    _logger.debug('Adding source breakpoint (empty line) at %s', pc)
                    new_breakpoint = self._create_breakpoint_at_pc(pc)
                    new_breakpoints.append(new_breakpoint)

                prev_line = end_line

        self._source_breakpoints[path] = new_breakpoints
        return [_breakpoint_json_data(bp) for bp in new_breakpoints]

    def stack_trace(self, start_frame, levels):
        frames = self._frame_data.frames

        if start_frame is None or levels is None:
            filter = lambda i: True
        else:
            filter = lambda i: start_frame <= i < start_frame + levels

        filtered_frames = [
            frame for i, frame in enumerate(frames)
            if filter(i)
        ]

        return filtered_frames, len(frames)

    def scopes(self, frame_id):
        return self._frame_data.scopes_by_frame[frame_id]

    def variables(self, variables_ref):
        return self._frame_data.variables_by_reference[variables_ref]

    def step_in(self):
        # Just execute one step, going inside a function if necessary.
        self._vm_step()
        self._compute_frame_data()

    def step_over(self):
        runner = self._runner
        current_stack_size = len(runner.vm.run_context.get_traceback_entries())
        while True:
            breakpoint_hit = self._vm_step()
            if breakpoint_hit:
                break
            new_current_stack_size = len(runner.vm.run_context.get_traceback_entries())
            # Exit when at the same stack location as the start.
            if new_current_stack_size <= current_stack_size:
                break
        self._compute_frame_data()

    def step_out(self):
        # Execute vm step until stack frame size is reduced by one.
        runner = self._runner
        current_stack_size = len(runner.vm.run_context.get_traceback_entries())
        if current_stack_size == 0:
            # inside main.
            self._vm_step()
            self._compute_frame_data()
        else:
            while True:
                breakpoint_hit = self._vm_step()
                if breakpoint_hit:
                    break
                new_current_stack_size = len(runner.vm.run_context.get_traceback_entries())
                # Exit when we're outside start stack location.
                if new_current_stack_size < current_stack_size:
                    break
            self._compute_frame_data()

    def has_exited(self):
        return self._runner.vm.run_context.pc == self._runner.final_pc

    def continue_until_breakpoint(self):
        while True:
            breakpoint_hit = self._vm_step()
            if breakpoint_hit or self.has_exited():
                break

        self._compute_frame_data()

    def program_output(self):
        if not self._has_relocated:
            yield from []
            return

        runner = self._runner
        if 'output_builtin' not in runner.builtin_runners:
            yield from []
            return

        output_runner = runner.builtin_runners['output_builtin']
        _, size = output_runner.get_used_cells_and_allocated_size(runner)
        for i in range(size):
            val = runner.vm_memory.get(output_runner.base + i)
            if val is not None:
                yield f'{to_field_element(val=val, prime=runner.program.prime)}'
            else:
                yield '<missing>'

    def _vm_step(self):
        runner = self._runner

        # Already at end of program
        if runner.vm.run_context.pc == runner.final_pc:
            return False

        runner.vm_step()

        source_breakpoints = [
            bp for breakpoints in self._source_breakpoints.values()
            for bp in breakpoints
        ]

        for breakpoint in self._function_breakpoints + source_breakpoints:
            if runner.vm.run_context.pc == breakpoint['pc']:
                return True

        return False

    def _create_breakpoint_at_pc(self, pc):
        frame = _frame_at_pc(self._cwd, self._runner, pc)
        return {
            'verified': True,
            'pc': pc,
            **frame,
        }

    def _compute_frame_data(self):
        # Compute stack frame data.
        # At each location we have the stack frame (current location + call stack),
        # each frame has several variables scope (locals + globals), each scope has
        # a collection of variables.
        #
        # The client will ask for this data in separate requests, but we compute
        # everything in this function.
        if self.has_exited():
            self._relocate()
            return

        frame_data = FrameData()
        cwd = self._cwd
        runner = self._runner

        frame, scopes_with_variables = _frame_data_at_pc(cwd, runner, runner.vm.run_context.pc)
        frame_data.add_frame_data(frame, scopes_with_variables)

        for traceback_pc in reversed(runner.vm.run_context.get_traceback_entries()):
            frame, scopes_with_variables = _frame_data_at_pc(cwd, runner, traceback_pc)
            frame_data.add_frame_data(frame, scopes_with_variables)

        self._frame_data = frame_data

    def _relocate(self):
        if self._has_relocated:
            return

        runner = self._runner
        runner.end_run()
        runner.finalize_segments_by_effective_size()
        runner.relocate()

        self._has_relocated = True


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
    pc_offset = pc - runner.program_base
    scope_name = runner.program.debug_info.instruction_locations[pc_offset].accessible_scopes[-1]
    scope_items = runner.program.identifiers.get_scope(scope_name).identifiers

    variables = []
    watch_evaluator = WatchEvaluator(runner, runner.program, runner.vm.run_context, runner.program_base)

    for name, identifier_definition in scope_items.items():
        if isinstance(identifier_definition, ReferenceDefinition):
            value = watch_evaluator.eval(name)
            variables.append({
                'name': name,
                'value': value,
                'variablesReference': 0,
            })
    return variables


def _breakpoint_json_data(bp):
    return dict((k, bp.get(k)) for k in ['id', 'verified', 'source', 'line', 'column', 'endLine', 'endColumn'])
