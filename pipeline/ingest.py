"""Converte um POP em DOCX/PDF para Markdown estruturado via markitdown."""

from pathlib import Path

from markitdown import MarkItDown


def pop_to_markdown(pop_path: str) -> str:
    path = Path(pop_path)
    if not path.exists():
        raise FileNotFoundError(f"POP não encontrado: {pop_path}")

    converter = MarkItDown()
    result = converter.convert(str(path))
    return result.text_content
