from tree_sitter import Language as TS_Language
import tree_sitter_javascript as tsjs

from src.indexer.parser import LanguageParser, MultiLanguageParser, UnitType


class JavaScriptParser(LanguageParser):
    @property
    def language(self) -> str:
        return "javascript"

    @property
    def file_extensions(self) -> list[str]:
        return [".js", ".mjs", ".cjs", ".jsx"]

    @property
    def language_binding(self) -> TS_Language:
        from tree_sitter import Language

        return Language(tsjs.language())

    def _map_node_type(self, node_type: str) -> UnitType:
        mapping = {
            "program": UnitType.FILE,
            "function_declaration": UnitType.FUNCTION,
            "class_declaration": UnitType.CLASS,
            "method_definition": UnitType.METHOD,
            "arrow_function": UnitType.FUNCTION,
            "lexical_declaration": UnitType.FUNCTION,
        }
        return mapping.get(node_type, UnitType.FILE)

    def _extract_name(self, node) -> str:
        for child in node.children:
            if child.type == "identifier" and child.text:
                return child.text.decode()
            if child.type == "property_identifier" and child.text:
                return child.text.decode()
        return ""


class TypeScriptParser(LanguageParser):
    @property
    def language(self) -> str:
        return "typescript"

    @property
    def file_extensions(self) -> list[str]:
        return [".ts", ".tsx", ".mts", ".cts"]

    @property
    def language_binding(self) -> TS_Language:
        from tree_sitter import Language
        import tree_sitter_typescript as tsts

        return Language(tsts.language_typescript())

    def _map_node_type(self, node_type: str) -> UnitType:
        mapping = {
            "program": UnitType.FILE,
            "function_declaration": UnitType.FUNCTION,
            "class_declaration": UnitType.CLASS,
            "method_definition": UnitType.METHOD,
            "arrow_function": UnitType.FUNCTION,
            "interface_declaration": UnitType.CLASS,
            "type_alias_declaration": UnitType.CLASS,
        }
        return mapping.get(node_type, UnitType.FILE)

    def _extract_name(self, node) -> str:
        for child in node.children:
            if child.type == "identifier" and child.text:
                return child.text.decode()
            if child.type == "property_identifier" and child.text:
                return child.text.decode()
        return ""


class TSXParser(LanguageParser):
    @property
    def language(self) -> str:
        return "tsx"

    @property
    def file_extensions(self) -> list[str]:
        return [".tsx"]

    @property
    def language_binding(self) -> TS_Language:
        from tree_sitter import Language
        import tree_sitter_typescript as tsts

        return Language(tsts.language_tsx())


MultiLanguageParser.register(JavaScriptParser)
MultiLanguageParser.register(TypeScriptParser)
MultiLanguageParser.register(TSXParser)


__all__ = ["JavaScriptParser", "TypeScriptParser", "TSXParser"]
