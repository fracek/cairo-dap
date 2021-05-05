# This code draws heavily from cairo-lang/src/starkware/cairo/lang/tracer/tracer_data.py
# Subject to the Cairo Toolchain License (Source Available)
from starkware.cairo.lang.compiler.ast.cairo_types import TypeStruct
from starkware.cairo.lang.compiler.ast.expr import ExprConst, ExprIdentifier
from starkware.cairo.lang.compiler.expression_evaluator import ExpressionEvaluator
from starkware.cairo.lang.compiler.identifier_definition import ConstDefinition, ReferenceDefinition
from starkware.cairo.lang.compiler.identifier_manager import MissingIdentifierError
from starkware.cairo.lang.compiler.identifier_utils import resolve_search_result
from starkware.cairo.lang.compiler.offset_reference import OffsetReferenceDefinition
from starkware.cairo.lang.compiler.parser import parse_expr
from starkware.cairo.lang.compiler.references import FlowTrackingError, SubstituteRegisterTransformer
from starkware.cairo.lang.compiler.scoped_name import ScopedName
from starkware.cairo.lang.compiler.substitute_identifiers import substitute_identifiers
from starkware.cairo.lang.compiler.type_system_visitor import simplify_type_system


class WatchEvaluator(ExpressionEvaluator):
    def __init__(self, runner, program, run_context, program_base):
        super().__init__(program.prime, ap=run_context.ap, fp=run_context.fp, memory=run_context.memory)

        self.runner = runner
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
        try:
            expr, expr_type = simplify_type_system(
                substitute_identifiers(
                    expr=parse_expr(expr),
                    get_identifier_callback=self.get_variable))
            if isinstance(expr_type, TypeStruct):
                raise NotImplementedError('Structs are not supported.')

            res = self.visit(expr)
            if isinstance(res, ExprConst):
                return str(res.val)
            return res.format()
        except FlowTrackingError:
            return ''
        except MissingIdentifierError:
            return ''

    def eval_suppress_errors(self, expr):
        try:
            return self.eval(expr)
        except Exception as exc:
            return f'{type(exc).__name__}: {exc}'

    def get_variable(self, var: ExprIdentifier):
        identifiers = self.program.identifiers
        identifier_definition = resolve_search_result(
            identifiers.search(
                accessible_scopes=self.accessible_scopes,
                name=ScopedName.from_string(var.name),
            ),
            identifiers=identifiers)
        if isinstance(identifier_definition, ConstDefinition):
            return identifier_definition.value

        if isinstance(identifier_definition, (ReferenceDefinition, OffsetReferenceDefinition)):
            return self.visit(self.eval_reference(identifier_definition, var.name))

        raise Exception(
            f'Unexpected identifier {var.name} of type {identifier_definition.TYPE}.')

    def eval_reference(self, identifier_definition, var_name: str):
        pc_offset = self.get_pc_offset(self.pc)
        current_flow_tracking_data = \
            self.program.debug_info.instruction_locations[pc_offset].flow_tracking_data
        try:
            substitute_transformer = SubstituteRegisterTransformer(
                ap=lambda location: ExprConst(val=self.ap, location=location),
                fp=lambda location: ExprConst(val=self.fp, location=location))
            return self.visit(substitute_transformer.visit(
                identifier_definition.eval(
                    reference_manager=self.program.reference_manager,
                    flow_tracking_data=current_flow_tracking_data)))
        except FlowTrackingError:
            raise FlowTrackingError(f"Invalid reference '{var_name}'.")

    def get_pc_offset(self, pc):
        return pc - self.program_base