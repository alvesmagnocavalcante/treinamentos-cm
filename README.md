# Treinamento interno com IA

MVP para cadastrar treinamentos, consultar procedimentos internos com RAG e gerar
roteiros com o CrewAI existente. As quatro fases estão implementadas. Vídeo,
avatar, TTS, login, quiz, progresso e certificados estão fora deste MVP.

## Arquitetura

```text
PDF/DOCX → extração por página/seção → chunking manual → Gemini Embeddings
    → ChromaDB → busca exclusiva por treinamento → contexto → OpenRouter
    → resposta com citações e trechos das fontes

Mesmo documento → MarkItDown → CrewAI (Extrator → Roteirista)
    → revisão humana no terminal → roteiro Markdown (sem vídeo)
```

FastAPI, Jinja2 e Bootstrap 5 servem as páginas; o chat usa fetch, sem SPA.
SQLite/SQLAlchemy mantém setores, treinamentos e documentos com chaves estrangeiras.
PyMuPDF extrai PDF; python-docx extrai DOCX, incluindo tabelas e títulos.
HTTPX comunica com Gemini e OpenRouter. O RAG não depende de LangChain ou CrewAI.
Chroma usa a collection persistente `hotel_training` com distância cosseno.

```text
app/
  main.py                 # inicialização e tratamento de erros
  config.py               # configuração via .env
  database.py, models.py   # SQLite e entidades
  routes/
    training.py           # páginas e cadastros
    documents.py          # upload, reindexação, download e exclusão
    chat.py               # endpoint de perguntas
  services/
    ingest.py, chunking.py, embeddings.py, vector_store.py
    documents.py, rag.py, llm.py, http.py, errors.py, roteiro.py
  templates/              # Jinja2
  static/                 # CSS e JavaScript
pipeline/                 # CLI, CrewAI, MarkItDown e cliente legado HeyGen
tests/                    # testes sem chamadas externas
media/documentos/         # originais com nome UUID, não versionados
vector_db/                # índice Chroma, não versionado
```

## Instalação — Windows PowerShell

Python 3.12+; validado com Python 3.12. Antes de atualizar dependências, encerre o
Uvicorn com Ctrl+C para liberar as DLLs do ambiente virtual no Windows.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Se o ambiente foi criado pelo uv e não possui pip:

```powershell
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
```

Não sobrescreva um `.env` já configurado. Preencha nele:

```dotenv
GOOGLE_API_KEY=sua-chave-google
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001
GEMINI_EMBEDDING_DIMENSIONS=768
OPENROUTER_API_KEY=sua-chave-openrouter
OPENROUTER_MODEL=openrouter/free
```

Obtenha a chave Google no Google AI Studio e a chave OpenRouter no painel do
OpenRouter. Disponibilidade e cotas dependem da conta e do modelo selecionado.
O chat usa o ID nativo do modelo; o formato legado `openrouter/anthropic/...`
também é normalizado. `CREWAI_MODEL` permite um modelo separado na roteirização.
Nunca versione chaves nem registre respostas brutas dos provedores em logs.

| Variável | Padrão | Uso |
|---|---|---|
| DATABASE_PATH | app/database/training.sqlite3 | SQLite |
| DOCUMENTS_PATH | media/documentos | arquivos originais |
| VECTOR_DB_PATH | vector_db | índice Chroma |
| MAX_UPLOAD_MB | 10 | tamanho máximo por arquivo |
| HTTP_TIMEOUT_SECONDS | 60 | timeout HTTP |
| CHUNK_TOKENS | 1000 | tamanho aproximado do chunk |
| CHUNK_OVERLAP_TOKENS | 150 | sobreposição aproximada |
| RAG_MAX_DISTANCE | 0.5 | distância cosseno máxima aceita |

Caminhos relativos são resolvidos a partir da raiz do projeto.

## Inicialização

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8765
```

Abra http://127.0.0.1:8765. A porta 8765 evita o bloqueio observado na porta 8000
neste Windows. Use um único processo local, sem múltiplos workers neste MVP.
O cadastro não exige chaves de IA. Bootstrap usa CDN e exige internet para estilização.

## Cadastro, upload e indexação

1. Abra **Cadastros** (`/admin`) e crie o setor **Recepção**.
2. Cadastre **Early Check-in**, informe descrição/conteúdo e mantenha **Ativo** marcado.
3. Abra o treinamento e clique em **Gerenciar documentos**.
4. Selecione o POP autorizado em PDF ou DOCX e clique em **Enviar e indexar**.
5. Aguarde o status **Indexado** após a extração e as chamadas ao Gemini.
6. Em caso de falha, o arquivo salvo permanece **Pendente**, sem entrar no chat.
   Corrija a configuração/cota/arquivo e use **Reindexar** ou **Excluir**.

Extensão, MIME e assinatura/estrutura interna são verificados. Arquivos recebem
nome UUID; nomes enviados pelo usuário não são usados como caminhos no disco.
Uploads multipart exigem Content-Length e os arquivos são copiados em blocos limitados.
DOCX é limitado a 50 MB descomprimidos e 2000 entradas; macros são rejeitadas.
PDF é limitado a 300 páginas. O texto é limitado a 2 milhões de caracteres e 1000 chunks.
PDFs sem texto exigem OCR prévio; não há OCR implementado.

Chunking manual estima 4 caracteres por token. Preserva parágrafos sempre que
possível e divide parágrafos muito longos com preferência por palavras completas.
Overlap ocorre dentro da página/seção; páginas e seções não são misturadas.
PDF guarda a página real. DOCX guarda o título da seção e retorna página nula,
pois não tem paginação estável. Cada chunk mantém documento, ID, treinamento,
setor, página e seção.

Reindexar remove chunks anteriores e evita duplicação. Em falhas, o documento
fica pendente e seus vetores antigos não entram no RAG. Excluir remove vetores,
arquivo e metadados. O SQLite controla quais documentos podem ser consultados.
Ao trocar modelo ou dimensões, configure um novo `VECTOR_DB_PATH` e reindexe todos
os documentos. A mistura de modelos/dimensões incompatíveis é bloqueada.

## Chat e fontes

1. Abra o treinamento e pergunte: **O que devo fazer quando o hóspede chega antes
   do horário de check-in?**
2. O backend pesquisa exclusivamente os documentos indexados desse treinamento.
3. Recupera até cinco chunks e elimina resultados acima da distância configurada.
4. Envia os trechos e a pergunta ao OpenRouter.
5. Exibe resposta, citações, nome do documento, página/seção e trechos citados.

```http
POST /treinamentos/1/perguntar
Content-Type: application/json

{"pergunta": "O que devo fazer quando o hóspede chega antes do horário de check-in?"}
```

```json
{
  "resposta": "Resposta fundamentada no documento [1].",
  "fontes": [{
    "id": 1,
    "documento_id": 1,
    "documento": "POP_EARLY_CHECKIN.pdf",
    "pagina": 3,
    "secao": "",
    "trecho": "Trecho recuperado do procedimento."
  }]
}
```

Sem documentos, sem trechos relevantes ou sem citação válida, retorna:
**Não encontrei essa informação nos documentos disponíveis.**
Somente fontes citadas são exibidas. Respostas com referências inexistentes são
descartadas. O prompt proíbe procedimentos inventados, conhecimento externo e
instruções embutidas nos documentos. Similaridade e citações não comprovam fidelidade
semântica: valide com seus POPs e confira os trechos. Calibre `RAG_MAX_DISTANCE`
com perguntas conhecidas e perguntas fora do escopo.

O histórico usa sessionStorage, limitado a 20 mensagens por treinamento, com botão
**Limpar conversa**. Não é enviado ao modelo: cada pergunta deve ser compreensível
sozinha. Não existe memória persistente.

## Roteirização existente com CrewAI

Na tabela de documentos, expanda **Gerar roteiro com revisão humana** e execute:

```powershell
python -m pipeline.run --documento-id 1
# Continua aceitando um arquivo diretamente:
python -m pipeline.run --pop caminho\para\pop.docx
```

O documento pode estar pendente de embeddings: a roteirização é independente do RAG.
MarkItDown mantém a conversão original; os agentes e prompts foram preservados.
O gate `human_input=True` exige terminal interativo. A página mostra o comando em
vez de tentar solicitar aprovação no stdin do servidor web.
O roteiro aprovado é salvo em `testdata/roteiro-aprovado-*.md`.
O CLI termina após salvar, sem importar ou chamar HeyGen. As variáveis antigas
de vídeo não reativam sua geração. O módulo legado foi preservado.

## Erros, segurança e operação

Ausência de chave, cota insuficiente, modelo indisponível, falha de rede e timeout
geram mensagens públicas sem credenciais ou respostas brutas. HTTP 429 é tratado
com orientação de espera; o endpoint JSON retorna Retry-After. Não há retries
automáticos que possam duplicar cobrança. Timeout não comprova cancelamento no
provedor: confira a conta antes de repetir a operação.

Há validação de entrada, consultas parametrizadas, escape HTML, renderização do
chat via textContent e bloqueio de POST com Origin diferente. Sem autenticação,
use apenas em ambiente local controlado. Não publique o servidor abertamente.
Texto dos documentos e perguntas vai ao Google; trechos recuperados vão ao OpenRouter.
Não envie dados de hóspedes ou informações financeiras sensíveis. Chamadas reais
devem ocorrer em testes controlados e autorizados.

Faça backup conjunto de SQLite, documentos e índice. As tabelas são criadas no
início; futuras mudanças de esquema exigirão migrações, pois create_all não altera
tabelas existentes.

## Testes e validações

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app pipeline tests
node --check app/static/chat.js
node --check app/static/documents.js
```

Testes cobrem PDF/DOCX gerados em memória, tabelas/seções, chunking,
Gemini/OpenRouter via MockTransport, Chroma persistente real, filtro por treinamento,
reindexação, exclusão, falhas, citações e endpoint completo. Também verificam a
estrutura real do CrewAI, seu gate humano e o CLI sem vídeo.
A rede HTTP externa está bloqueada nos testes. O cenário Early Check-in usa
conteúdo **fictício**, não um procedimento oficial do hotel.

Validação externa ainda necessária: configurar as chaves, enviar o POP real e
conferir resposta e página contra o documento. Mocks não validam credenciais,
disponibilidade dos modelos ou qualidade das respostas reais.

## Referências das integrações

- [Gemini Embeddings — API REST](https://ai.google.dev/api/embeddings)
- [Chroma — filtros de metadados](https://docs.trychroma.com/docs/querying-collections/metadata-filtering)
- [OpenRouter — API](https://openrouter.ai/docs/api/reference/overview)
- [OpenRouter — tratamento de erros](https://openrouter.ai/docs/api/reference/errors-and-debugging)
