"""POP -> Markdown -> Crew (com gate humano) -> roteiro. Vídeo desativado no MVP."""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from app.config import Settings
from app.services.errors import ServiceError
from app.services.roteiro import document_path, generate_script

PADRAO_ETAPA = re.compile(r"^\s*\d+\.", re.MULTILINE)
PADRAO_CENA = re.compile(r"CENA\s*\d+", re.IGNORECASE)
PADRAO_AMBIGUO = re.compile(r"\[AMBÍGUO:[^\]]*\]", re.IGNORECASE)
PADRAO_CRITICO_SIM = re.compile(r"Ponto cr[ií]tico:\s*\*{0,2}Sim", re.IGNORECASE)
PADRAO_ATENCAO = re.compile(r"ATEN[ÇC][ÃA]O", re.IGNORECASE)


def validar_fidelidade(extracao: str, roteiro: str) -> None:
    """Checagem best-effort (regex, não garante 100% de precisão) para pegar
    perda óbvia de conteúdo entre a extração e o roteiro final antes do gate
    humano: quantidade de etapas vs. cenas, e ambiguidades sinalizadas que
    sumiram no roteiro."""
    n_etapas = len(PADRAO_ETAPA.findall(extracao))
    n_cenas = len(set(m.upper() for m in PADRAO_CENA.findall(roteiro)))
    if n_etapas and n_cenas and n_etapas != n_cenas:
        print(
            f"[AVISO] Extração tem {n_etapas} etapa(s) numeradas, mas o roteiro "
            f"tem {n_cenas} cena(s) — confira se nenhuma etapa foi fundida ou "
            "esquecida antes de aprovar no gate humano."
        )

    ambiguidades_extracao = PADRAO_AMBIGUO.findall(extracao)
    ambiguidades_roteiro = PADRAO_AMBIGUO.findall(roteiro)
    if len(ambiguidades_extracao) > len(ambiguidades_roteiro):
        print(
            f"[AVISO] {len(ambiguidades_extracao)} ambiguidade(s) sinalizada(s) na "
            f"extração, mas só {len(ambiguidades_roteiro)} aparecem no roteiro — "
            "confira se o Roteirista resolveu ou omitiu alguma por conta própria."
        )

    n_criticos = len(PADRAO_CRITICO_SIM.findall(extracao))
    n_atencao = len(PADRAO_ATENCAO.findall(roteiro))
    if n_atencao > n_criticos:
        print(
            f"[AVISO] Extração marcou {n_criticos} etapa(s) como ponto crítico, "
            f"mas o roteiro usa a tag 'ATENÇÃO' {n_atencao} vez(es) — confira se "
            "o Roteirista está aplicando a tag em etapas não críticas."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="POP -> roteiro de treinamento (sem vídeo)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pop", help="Caminho para o POP (DOCX/PDF)")
    source.add_argument("--documento-id", type=int, help="ID de um documento enviado pela aplicação web")
    args = parser.parse_args()

    # O gate humano (crew.py, human_input=True) usa o provider padrão do CrewAI, que
    # chama input() builtin sem checar se há stdin interativo (confirmado na doc oficial:
    # crewai.core.providers.human_input.SyncHumanInputProvider._prompt_input). Sem essa
    # checagem, rodar com saída redirecionada faz o Crew estourar EOFError no meio da
    # execução (foi o que aconteceu nas 3 tentativas anteriores, ver testdata/run*.log).
    # Falhar aqui, cedo e com mensagem clara, em vez de deixar o traceback cru aparecer
    # depois de já ter gasto a chamada ao OpenRouter.
    if not sys.stdin.isatty():
        sys.exit(
            "Este piloto exige um terminal interativo real: o gate humano obrigatório "
            "(pipeline/crew.py, human_input=True) espera aprovação digitada via input() "
            "antes de salvar o roteiro. Rode `python -m pipeline.run --pop <arquivo>` "
            "direto num terminal, sem redirecionar a saída para arquivo/pipe."
        )

    try:
        path = str(document_path(args.documento_id, Settings.from_env())) if args.documento_id is not None else args.pop
    except ServiceError as exc:
        parser.error(str(exc))
    print(f"[1/4] Convertendo POP para Markdown: {path}")
    print("[2/4] Rodando Crew (Extrator -> Roteirista)...")
    extracao, resultado = generate_script(path)
    validar_fidelidade(extracao, str(resultado))

    print("\n[3/4] Roteiro final (aprovado via gate humano do CrewAI):\n")
    print(resultado)

    saida_dir = Path(__file__).resolve().parent.parent / "testdata"
    saida_dir.mkdir(exist_ok=True)
    caminho_roteiro = saida_dir / f"roteiro-aprovado-{datetime.now():%Y%m%d-%H%M%S}.md"
    caminho_roteiro.write_text(str(resultado), encoding="utf-8")
    print(f"\nRoteiro salvo em: {caminho_roteiro}")

    print("\n[4/4] Roteirização concluída. Geração de vídeo desativada neste MVP.")


if __name__ == "__main__":
    main()
