"""Safe calculator tool — restricted AST evaluation, never eval/exec."""

from __future__ import annotations

import ast
import operator
from typing import Any, ClassVar

from pydantic import BaseModel, Field, field_validator

from app.tools.base import BaseTool
from app.tools.context import ToolExecutionContext
from app.tools.exceptions import ToolExecutionFailedError, ToolInvalidArgumentsError
from app.tools.schemas import ToolResultPayload

_MAX_EXPRESSION_LENGTH = 200
_MAX_ABS_NUMBER = 1e15
_MAX_EXPONENT = 12

_BINARY_OPS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type[ast.unaryop], Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class CalculatorInput(BaseModel):
    expression: str = Field(min_length=1, max_length=_MAX_EXPRESSION_LENGTH)

    @field_validator("expression")
    @classmethod
    def strip_expression(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Expression cannot be blank")
        return cleaned


class CalculatorOutput(BaseModel):
    expression: str
    result: float | int


def _safe_eval_node(node: ast.AST) -> float | int:
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body)
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, int | float)
        and not isinstance(node.value, bool)
    ):
        value = node.value
        if abs(value) > _MAX_ABS_NUMBER:
            raise ToolInvalidArgumentsError("Number magnitude exceeds allowed limit")
        return value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        value = _UNARY_OPS[type(node.op)](_safe_eval_node(node.operand))
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise ToolInvalidArgumentsError("Unsupported expression syntax")
        return value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        if isinstance(node.op, ast.Pow):
            if not isinstance(right, int) or abs(right) > _MAX_EXPONENT:
                raise ToolInvalidArgumentsError(
                    f"Exponent must be an integer within ±{_MAX_EXPONENT}"
                )
            if abs(left) > 1e6 and abs(right) > 6:
                raise ToolInvalidArgumentsError("Exponentiation result would be too large")
        if isinstance(node.op, ast.Div | ast.Mod) and right == 0:
            raise ToolExecutionFailedError("Division by zero")
        # Percentage: treat `a % b` as modulo only; percentage of X is via expression.
        result = _BINARY_OPS[type(node.op)](left, right)
        if isinstance(result, complex):
            raise ToolInvalidArgumentsError("Complex results are not supported")
        if not isinstance(result, int | float) or isinstance(result, bool):
            raise ToolInvalidArgumentsError("Unsupported expression syntax")
        if abs(result) > _MAX_ABS_NUMBER:
            raise ToolInvalidArgumentsError("Result magnitude exceeds allowed limit")
        return result
    # Support `pct%` as percentage of 100 via `pct / 100` rewrite is not AST-native.
    # Support percentage operator form: `N % of M` is not supported; use (N * M) / 100.
    raise ToolInvalidArgumentsError("Unsupported expression syntax")


def evaluate_expression(expression: str) -> float | int:
    """Evaluate a safe arithmetic expression.

    Supports + - * / % ** and parentheses. Percentage of a value should be
    written as ``(value * percent) / 100``.
    """
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise ToolInvalidArgumentsError("Expression is too long")
    # Reject obvious dangerous tokens before parse.
    lowered = expression.lower()
    for banned in ("__", "import", "eval", "exec", "open", "lambda", "class"):
        if banned in lowered:
            raise ToolInvalidArgumentsError("Unsupported expression syntax")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolInvalidArgumentsError("Unsupported expression syntax") from exc
    result = _safe_eval_node(tree)
    if isinstance(result, float) and result.is_integer():
        return int(result)
    return result


class CalculatorTool(BaseTool):
    name: ClassVar[str] = "calculator"
    description: ClassVar[str] = (
        "Evaluate a safe arithmetic expression. Supports +, -, *, /, %, **, and "
        "parentheses. For percentages use (value * percent) / 100. "
        "Example: (1200 * 15) / 100."
    )
    version: ClassVar[str] = "1.0.0"
    category: ClassVar[str] = "math"
    input_model: ClassVar[type[BaseModel]] = CalculatorInput
    output_model: ClassVar[type[BaseModel] | None] = CalculatorOutput
    timeout_seconds: ClassVar[int] = 5

    async def execute(
        self,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> ToolResultPayload:
        assert isinstance(arguments, CalculatorInput)
        _ = context
        result = evaluate_expression(arguments.expression)
        payload = CalculatorOutput(expression=arguments.expression, result=result)
        return ToolResultPayload(success=True, data=payload.model_dump())
