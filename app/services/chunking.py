import re
from dataclasses import dataclass

from app.services.ingest import TextSection


@dataclass(frozen=True)
class Chunk:
    text: str
    page: int
    section: str


def chunk_sections(sections: list[TextSection], size_tokens: int = 1000, overlap_tokens: int = 150) -> list[Chunk]:
    """Estimativa local de 4 caracteres/token; preserva parágrafos e páginas/seções."""
    if not 0 <= overlap_tokens < size_tokens:
        raise ValueError("Overlap deve ser menor que o tamanho do chunk.")
    limit, overlap = size_tokens * 4, overlap_tokens * 4
    chunks = []
    for section in sections:
        units = []
        for paragraph in re.split(r"\n\s*\n", section.text.strip()):
            paragraph = paragraph.strip()
            while len(paragraph) > limit:
                boundary = paragraph.rfind(" ", 0, limit)
                boundary = boundary if boundary > limit // 2 else limit
                units.append(paragraph[:boundary])
                paragraph = paragraph[boundary:].lstrip()
            if paragraph:
                units.append(paragraph)
        current = ""
        for unit in units:
            if current and len(current) + len(unit) + 2 > limit:
                chunks.append(Chunk(current, section.page, section.section))
                tail = current[-overlap:] if overlap else ""
                # Começar o overlap em palavra completa.
                if tail and len(current) > overlap and " " in tail:
                    tail = tail.split(" ", 1)[1]
                current = tail if len(tail) + len(unit) + 2 <= limit else ""
            current = f"{current}\n\n{unit}" if current else unit
        if current:
            chunks.append(Chunk(current, section.page, section.section))
    return chunks
