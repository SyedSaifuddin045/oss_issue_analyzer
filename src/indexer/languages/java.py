from tree_sitter import Language as TS_Language

from src.indexer.parser import LanguageParser, MultiLanguageParser, UnitType


class JavaParser(LanguageParser):
    @property
    def language(self) -> str:
        return "java"

    @property
    def file_extensions(self) -> list[str]:
        return [".java"]

    @property
    def language_binding(self) -> TS_Language:
        from tree_sitter import Language
        import tree_sitter_java as tsjava

        return Language(tsjava.language())

    def _map_node_type(self, node_type: str) -> UnitType:
        mapping = {
            "program": UnitType.FILE,
            "class_declaration": UnitType.CLASS,
            "interface_declaration": UnitType.CLASS,
            "enum_declaration": UnitType.CLASS,
            "annotation_type_declaration": UnitType.CLASS,
            "method_declaration": UnitType.METHOD,
            "constructor_declaration": UnitType.METHOD,
        }
        return mapping.get(node_type, UnitType.FILE)

    def _extract_name(self, node) -> str:
        for child in node.children:
            if child.type == "identifier" and child.text:
                return child.text.decode()
        return ""


MultiLanguageParser.register(JavaParser)


__all__ = ["JavaParser"]
