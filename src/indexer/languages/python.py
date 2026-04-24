from tree_sitter import Language as TS_Language

import tree_sitter_python as tspython

from src.indexer.parser import LanguageParser, MultiLanguageParser, UnitType


class PythonParser(LanguageParser):
    @property
    def language(self) -> str:
        return "python"

    @property
    def file_extensions(self) -> list[str]:
        return [".py", ".pyw", ".pyi"]

    @property
    def language_binding(self) -> TS_Language:
        from tree_sitter import Language

        return Language(tspython.language())

    def _map_node_type(self, node_type: str) -> UnitType:
        mapping = {
            "module": UnitType.FILE,
            "function_definition": UnitType.FUNCTION,
            "class_definition": UnitType.CLASS,
            "async_function_definition": UnitType.FUNCTION,
            "method_definition": UnitType.METHOD,
        }
        return mapping.get(node_type, UnitType.FILE)

    def _extract_name(self, node) -> str:
        if node.type in ("function_definition", "class_definition", "async_function_definition"):
            for child in node.children:
                if child.type == "identifier":
                    text = child.text
                    if text:
                        return text.decode()
        if node.type == "method_definition":
            for child in node.children:
                if child.type == "identifier":
                    text = child.text
                    if text:
                        return text.decode()
        return ""

    def _extract_signature(self, node, source: str) -> str:
        if node.type in (
            "function_definition",
            "async_function_definition",
            "method_definition",
        ):
            for param_node in node.children:
                if param_node.type == "parameters":
                    text = param_node.text
                    if text:
                        return text.decode()
        return ""

    def _extract_docstring(self, node, source: str) -> str:
        if node.type in (
            "function_definition",
            "class_definition",
            "async_function_definition",
            "method_definition",
        ):
            for i, child in enumerate(node.children):
                if child.type == "block":
                    if child.children:
                        first_stmt = child.children[0]
                        if first_stmt.type == "expression_statement":
                            expr = first_stmt.children[0]
                            if expr.type == "string":
                                text = expr.text
                                if text:
                                    return text.decode()[1:-1]
        return ""


MultiLanguageParser.register(PythonParser)


__all__ = ["PythonParser"]
