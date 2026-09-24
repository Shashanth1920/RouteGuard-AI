"""Tool 1: calculator (low risk). No eval() - eval("__import__('os').system(...)")
would run arbitrary code. Instead the expression is parsed into an AST and only
number/+-*/ nodes are allowed to actually run; anything else (names, calls,
attributes, imports) is rejected before it can execute."""
import ast
import operator

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


# A whitelist of safe node types isn't enough on its own: `2**999999999999`
# is valid arithmetic but Python's bigint pow() will spend unbounded time
# and memory computing it (confirmed live - it grew a process to several
# GB before being killed). Cap exponents so ** can't be used as a DoS tool.
_MAX_EXPONENT = 1000


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
            raise ValueError("exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError("expression not allowed")


def calculate(expression: str) -> dict:
    try:
        tree = ast.parse(expression, mode="eval")
        return {"result": _eval_node(tree.body), "error": None}
    except ZeroDivisionError:
        return {"result": None, "error": "division by zero"}
    except (SyntaxError, ValueError, TypeError):
        return {"result": None, "error": "invalid expression"}
