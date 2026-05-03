from tree_sitter import Language as TS_Language

from src.indexer.parser import LanguageParser, MultiLanguageParser, UnitType


class CParser(LanguageParser):
    @property
    def language(self) -> str:
        return "c"

    @property
    def file_extensions(self) -> list[str]:
        return [".c", ".h"]

    @property
    def language_binding(self) -> TS_Language:
        from tree_sitter import Language
        import tree_sitter_c as tsc

        return Language(tsc.language())

    def _map_node_type(self, node_type: str) -> UnitType:
        mapping = {
            "translation_unit": UnitType.FILE,
            "function_definition": UnitType.FUNCTION,
            "struct_specifier": UnitType.CLASS,
            "union_specifier": UnitType.CLASS,
            "enum_specifier": UnitType.CLASS,
        }
        return mapping.get(node_type, UnitType.FILE)

    def _extract_name(self, node) -> str:
        for child in node.children:
            if child.type in {"identifier", "type_identifier", "field_identifier"} and child.text:
                return child.text.decode()
        return ""


class CppParser(LanguageParser):
    @property
    def language(self) -> str:
        return "cpp"

    @property
    def file_extensions(self) -> list[str]:
        return [".cc", ".cpp", ".cxx", ".hpp", ".hh", ".hxx"]

    @property
    def language_binding(self) -> TS_Language:
        from tree_sitter import Language
        import tree_sitter_cpp as tscpp

        return Language(tscpp.language())

    def _map_node_type(self, node_type: str) -> UnitType:
        mapping = {
            "translation_unit": UnitType.FILE,
            "function_definition": UnitType.FUNCTION,
            "class_specifier": UnitType.CLASS,
            "struct_specifier": UnitType.CLASS,
            "namespace_definition": UnitType.CLASS,
            "field_initializer_list": UnitType.METHOD,
        }
        return mapping.get(node_type, UnitType.FILE)

    def _extract_name(self, node) -> str:
        for child in node.children:
            if child.type in {"identifier", "type_identifier", "field_identifier", "namespace_identifier"} and child.text:
                return child.text.decode()
        return ""


MultiLanguageParser.register(CParser)
MultiLanguageParser.register(CppParser)


__all__ = ["CParser", "CppParser"]
