"""Small FFmpeg expression evaluator used for static output geometry checks."""

from __future__ import annotations

import ast
import math
from collections.abc import Callable, Mapping
from typing import cast


class ExpressionError(ValueError):
    pass


def resolve_dimensions(
    width: str,
    height: str,
    *,
    input_width: int,
    input_height: int,
) -> tuple[int, int]:
    """Resolve ow/oh references as a graph and reject cyclic geometry."""
    expressions = {"ow": width, "oh": height}
    resolved: dict[str, int] = {}
    visiting: set[str] = set()

    def resolve(name: str) -> int:
        if name in resolved:
            return resolved[name]
        if name in visiting:
            raise ExpressionError("cyclic ow/oh dimension dependency")
        visiting.add(name)
        try:
            tree = ast.parse(expressions[name], mode="eval")
        except SyntaxError as exc:
            raise ExpressionError(
                f"invalid dimension expression {expressions[name]!r}"
            ) from exc
        result = _evaluate(
            tree.body,
            {
                "iw": input_width,
                "in_w": input_width,
                "ih": input_height,
                "in_h": input_height,
            },
            resolve,
        )
        if not math.isfinite(result) or int(result) != result:
            raise ExpressionError(
                "dimension expression must resolve to a finite integer"
            )
        visiting.remove(name)
        resolved[name] = int(result)
        return resolved[name]

    return resolve("ow"), resolve("oh")


def evaluate_offset(expression: str, *, iw: int, ih: int, ow: int, oh: int) -> int:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ExpressionError(f"invalid dimension expression {expression!r}") from exc
    result = _evaluate(
        tree.body,
        {
            "iw": iw,
            "in_w": iw,
            "ih": ih,
            "in_h": ih,
            "ow": ow,
            "out_w": ow,
            "oh": oh,
            "out_h": oh,
        },
        lambda _: 0,
    )
    if not math.isfinite(result) or int(result) != result:
        raise ExpressionError("dimension expression must resolve to a finite integer")
    return int(result)


def _evaluate(
    node: ast.expr, values: Mapping[str, float], resolve: Callable[[str], int]
) -> float:
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        return float(cast(int | float, node.value))
    if isinstance(node, ast.Name):
        if node.id in values:
            return values[node.id]
        if node.id in {"ow", "out_w"} or node.id in {"oh", "out_h"}:
            return float(resolve("ow" if node.id in {"ow", "out_w"} else "oh"))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate(node.operand, values, resolve)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left, right = (
            _evaluate(node.left, values, resolve),
            _evaluate(node.right, values, resolve),
        )
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ExpressionError("division by zero in dimension expression")
            return left / right
        if isinstance(node.op, ast.Mod):
            if right == 0:
                raise ExpressionError("division by zero in dimension expression")
            return left % right
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.keywords:
            raise ExpressionError("dimension functions do not accept keywords")
        args = [_evaluate(arg, values, resolve) for arg in node.args]
        if node.func.id in {"min", "max"} and len(args) >= 2:
            return min(args) if node.func.id == "min" else max(args)
        if node.func.id in {"floor", "ceil", "trunc"} and len(args) == 1:
            if node.func.id == "floor":
                return float(math.floor(args[0]))
            if node.func.id == "ceil":
                return float(math.ceil(args[0]))
            return float(math.trunc(args[0]))
    raise ExpressionError("dimension expression uses unsupported FFmpeg syntax")
