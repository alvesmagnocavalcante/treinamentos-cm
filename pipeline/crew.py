"""Crew de 2 agentes: Extrator (identifica etapas/pontos críticos do POP) e
Roteirista (transforma as etapas em roteiro de narração + cenas). O roteiro final
passa por um gate humano (human_input=True) antes de qualquer geração de vídeo.
"""

import os

from crewai import Agent, Crew, Process, Task
from dotenv import load_dotenv

load_dotenv()

LLM_MODEL = os.environ.get("CREWAI_MODEL") or os.environ.get("OPENROUTER_MODEL", "openrouter/free")
if not LLM_MODEL.startswith("openrouter/"):
    LLM_MODEL = f"openrouter/{LLM_MODEL}"
# O ID nativo openrouter/free precisa do prefixo adicional do adaptador CrewAI.
if LLM_MODEL == "openrouter/free":
    LLM_MODEL = "openrouter/openrouter/free"

# Identidade visual da Carmel Hotéis (carmelhoteis.com.br), usada apenas como
# referência de tom/paleta para a descrição visual das cenas — este é um vídeo de
# treinamento interno, não uma peça de marketing.
DIRETRIZES_VISUAIS_CARMEL = (
    "Paleta: azul petróleo/marinho escuro como cor de base, com dourado ou branco "
    "para texto/detalhes; ambiente litorâneo cearense (quando fizer sentido para o "
    "procedimento) com elementos naturais discretos. Tipografia elegante, sóbria. "
    "Tom geral: 'luxo de pés descalços' — sofisticado mas acolhedor, nunca "
    "espalhafatoso. Como é vídeo de treinamento interno, priorize clareza e "
    "profissionalismo sobre apelo estético; a identidade visual deve aparecer em "
    "fundo, lower-thirds e paleta de cores, não como foco da cena."
)


def build_crew(pop_markdown: str) -> Crew:
    extrator = Agent(
        role="Extrator de POP",
        goal="Identificar as etapas do procedimento e os pontos críticos de segurança/qualidade",
        backstory=(
            "Você lê procedimentos operacionais padrão (POPs) de uma rede hoteleira e "
            "extrai a sequência de etapas executáveis, sem inventar, resumir demais "
            "ou reordenar passos que não estão explícitos no texto original. Se o POP "
            "for ambíguo ou incompleto em algum ponto, você sinaliza a ambiguidade em "
            "vez de preencher a lacuna com suposição."
        ),
        llm=LLM_MODEL,
        verbose=True,
    )

    roteirista = Agent(
        role="Roteirista de treinamento",
        goal="Transformar as etapas extraídas em um roteiro de narração dividido em cenas",
        backstory=(
            "Você escreve roteiros de vídeo de treinamento curtos e diretos para "
            "colaboradores da rede hoteleira Carmel Hotéis, uma cena por etapa do "
            "procedimento, com texto de narração (frases curtas, linguagem falada, "
            "sem jargão desnecessário) e descrição visual da cena alinhada à "
            "identidade visual da marca. Você nunca adiciona informação operacional "
            "que não veio da etapa extraída — a licença criativa é só na forma "
            "(narração, cenas, visual), nunca no conteúdo do procedimento."
        ),
        llm=LLM_MODEL,
        verbose=True,
    )

    tarefa_extracao = Task(
        description=(
            "Leia o POP abaixo (em Markdown) e liste as etapas do procedimento em "
            "ordem, marcando quais são pontos críticos (segurança, qualidade, "
            "compliance). Só marque uma etapa como ponto crítico ('sim') se o POP "
            "descreve uma consequência concreta de erro/atraso/omissão nessa etapa "
            "(ex.: prazo com penalidade, dado que compromete etapas seguintes, "
            "exigência formal de compliance). Etapas apenas descritivas de um passo "
            "do fluxo, sem consequência declarada, são 'não' — mesmo que pareçam "
            "importantes. Não invente etapas nem preencha lacunas — se algo estiver "
            "ambíguo, marque como '[AMBÍGUO: ...]' em vez de assumir.\n\n"
            "POP:\n---\n{pop_markdown}\n---"
        ),
        expected_output=(
            "Lista numerada de etapas, cada uma com: texto da etapa, se é ponto "
            "crítico (sim/não + motivo citando a consequência concreta, quando "
            "'sim') e eventuais ambiguidades sinalizadas."
        ),
        agent=extrator,
    )

    tarefa_roteiro = Task(
        description=(
            "A partir das etapas extraídas, escreva o roteiro de narração dividido em "
            "cenas (uma cena por etapa, na mesma ordem). Para cada cena, produza:\n"
            "- Narração: texto curto (até ~3 frases), em português, tom acolhedor e "
            "direto, como se um colega experiente explicasse o passo.\n"
            "- Visual: descrição da cena (ambiente, ação, texto em tela se houver), "
            "seguindo as diretrizes visuais abaixo.\n"
            "- Use a tag 'ATENÇÃO' na narração e no visual SOMENTE quando a etapa "
            "extraída foi marcada pelo Extrator como ponto crítico ('sim'). Não "
            "aplique a tag por conta própria em etapas marcadas como 'não' — mesmo "
            "que pareçam importantes ao seu julgamento. A tag precisa continuar "
            "rara para funcionar como destaque; usá-la em toda cena a esvazia.\n"
            "- Quando usar a tag, a narração precisa citar a consequência concreta "
            "que o Extrator apontou como motivo (ex.: o que acontece se o prazo "
            "não for cumprido) — não basta inserir 'ATENÇÃO' antes de uma descrição "
            "neutra do passo.\n"
            "- Se a etapa extraída tiver uma marcação '[AMBÍGUO: ...]', copie essa "
            "marcação (o texto entre colchetes) para dentro da cena correspondente, "
            "de forma visível — nunca resolva a ambiguidade por conta própria nem a "
            "remova do roteiro final.\n\n"
            f"Diretrizes visuais da marca:\n{DIRETRIZES_VISUAIS_CARMEL}"
        ),
        expected_output=(
            "Roteiro dividido em cenas numeradas (mesma quantidade e ordem das "
            "etapas extraídas), cada uma com narração e descrição visual. Toda "
            "marcação '[AMBÍGUO: ...]' presente nas etapas extraídas deve aparecer "
            "na cena correspondente, sem ser resolvida ou omitida. A tag 'ATENÇÃO' "
            "aparece só nas cenas cuja etapa foi marcada como ponto crítico pelo "
            "Extrator — nas demais, nem narração nem visual mencionam 'ATENÇÃO'."
        ),
        agent=roteirista,
        context=[tarefa_extracao],
        human_input=True,
    )

    return Crew(
        agents=[extrator, roteirista],
        tasks=[tarefa_extracao, tarefa_roteiro],
        process=Process.sequential,
    )
