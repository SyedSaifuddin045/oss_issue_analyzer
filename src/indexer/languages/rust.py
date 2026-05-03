from tree_sitter import Language as TS_Language

from src.indexer.parser import LanguageParser, MultiLanguageParser, UnitType


class RustParser(LanguageParser):
    @property
    def language(self) -> str:
        return "rust"

    @property
    def file_extensions(self) -> list[str]:
        return [".rs"]

    @property
    def language_binding(self) -> TS_Language:
        from tree_sitter import Language
        import tree_sitter_rust as tsrust

        return Language(tsrust.language())

    def _map_node_type(self, node_type: str) -> UnitType:
        mapping = {
            "source_file": UnitType.FILE,
            "function_item": UnitType.FUNCTION,
            "impl_item": UnitType.CLASS,
            "struct_item": UnitType.CLASS,
            "enum_item": UnitType.CLASS,
            "trait_item": UnitType.CLASS,
        }
        return mapping.get(node_type, UnitType.FILE)

    def _extract_name(self, node) -> str:
        for child in node.children:
            if child.type in {"identifier", "type_identifier"} and child.text:
                return child.text.decode()
        return ""


MultiLanguageParser.register(RustParser)


__all__ = ["RustParser"]
