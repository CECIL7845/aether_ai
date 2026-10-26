"""Safe arithmetic evaluation: parses the expression into an AST and only evaluates numeric operations."""

from __future__ import annotations

import ast
import math
import operator
import re

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"abs": abs, "round": round, "sqrt": math.sqrt, "log": math.log, "log10": math.log10, "exp": math.exp,
          "min": min, "max": max, "ceil": math.ceil, "floor": math.floor}
_CONSTS = {"pi": math.pi, "e": math.e}


class CalcError(ValueError):
    pass


def evaluate(expression: str) -> float | int:
    if len(expression) > 300:
        raise CalcError("Expression is too long.")
    try:
        # Drop thousands separators ("1,200") but keep commas that separate function arguments.
        cleaned = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", expression).replace("^", "**")
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as e:
        raise CalcError("Expression is not valid arithmetic.") from e
    return _eval(tree.body)


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in _CONSTS:
        return _CONSTS[node.id]
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 1000 or abs(left) > 1e12):
            raise CalcError("Exponent is too large.")
        try:
            return _BIN[type(node.op)](left, right)
        except ZeroDivisionError as e:
            raise CalcError("Division by zero.") from e
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
        try:
            return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
        except (TypeError, ValueError) as e:
            raise CalcError(f"Invalid arguments to {node.func.id}().") from e
    raise CalcError("Only numbers, + - * / ** %, parentheses and basic math functions are allowed.")
