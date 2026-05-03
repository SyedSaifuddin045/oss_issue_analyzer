from tree_sitter import Language as TS_Language

from src.indexer.parser import LanguageParser, MultiLanguageParser, UnitType


class GoParser(LanguageParser):
    @property
    def language(self) -> str:
        return "go"

    @property
    def file_extensions(self) -> list[str]:
        return [".go"]

    @property
    def language_binding(self) -> TS_Language:
        from tree_sitter import Language
        import tree_sitter_go as tsgo

        return Language(tsgo.language())

    def _map_node_type(self, node_type: str) -> UnitType:
        mapping = {
            "source_file": UnitType.FILE,
            "function_declaration": UnitType.FUNCTION,
            "method_declaration": UnitType.METHOD,
            "type_declaration": UnitType.CLASS,
        }
        return mapping.get(node_type, UnitType.FILE)

    def _extract_name(self, node) -> str:
        for child in node.children:
            if child.type == "identifier" and child.text:
                return child.text.decode()
            if child.type == "type_identifier" and child.text:
                return child.text.decode()
            if child.type == "field_identifier" and child.text:
                return child.text.decode()
        return ""


MultiLanguageParser.register(GoParser)


__all__ = ["GoParser"]
