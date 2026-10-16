# Academia Carmel

Plataforma Django para treinamentos internos. O colaborador entra com seu usuário,
seleciona um treinamento, acompanha suas aulas, consulta materiais e tira dúvidas
no chat com RAG. A administração usa o Django Admin.

Cada treinamento pode ter várias aulas, ordenadas, com vídeo opcional do Google
Drive e explicação em texto. Os documentos PDF/DOCX pertencem ao treinamento e
alimentam o RAG. Vídeos e textos das aulas não são indexados automaticamente.
A geração de roteiros foi retirada por enquanto; não há integração com HeyGen ou n8n.

## Instalação e execução com uv

Python 3.12, indicado em `.python-version`. Dependências e versões estão em
`pyproject.toml` e `uv.lock`. Não é necessário ativar o ambiente virtual.

```powershell
uv sync --locked
# Execute a cópia somente se ainda não existir um .env:
Copy-Item .env.example .env
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver 127.0.0.1:8765
```

Não sobrescreva um `.env` configurado. O servidor anterior de FastAPI/Uvicorn
deve estar encerrado antes de usar a mesma porta. O comando de inicialização
agora é `manage.py runserver`.

- Colaborador: http://127.0.0.1:8765/
- Administração: http://127.0.0.1:8765/admin/
- Login: http://127.0.0.1:8765/conta/entrar/

O login é obrigatório. Não há contas ou senhas padrão. O superusuário é criado
pelo comando interativo acima. Crie os colaboradores em **Usuários** no Admin,
sem marcar **Membro da equipe** ou **Superusuário**.

Em desenvolvimento, se `DJANGO_SECRET_KEY` estiver vazio, uma chave aleatória
persistente é criada em `.cache/django-secret`, ignorada pelo Git. Fora do
ambiente local, configure explicitamente a chave, os hosts permitidos e HTTPS.

## Importar dados da versão anterior

O banco Django padrão é `app/database/platform.sqlite3`. O SQLite anterior,
`app/database/training.sqlite3`, permanece separado.

Com as migrações já aplicadas:

```powershell
uv run python manage.py import_legacy
# Ou informe explicitamente o arquivo:
uv run python manage.py import_legacy --database caminho/para/training.sqlite3
```

A importação lê a origem em modo somente leitura e preserva os IDs de setores,
treinamentos e documentos. Isso mantém a referência dos vetores Chroma existentes.
O vídeo e o conteúdo antigos tornam-se a primeira aula de cada treinamento.
Os arquivos originais permanecem em `DOCUMENTS_PATH`; nenhum documento é copiado,
apagado ou enviado a provedores de IA durante a importação.

Reexecutar a importação com dados inalterados não duplica registros. IDs ou aulas
conflitantes interrompem toda a transação sem sobrescrever alterações no destino.
Arquivos ausentes são importados como pendentes. Não importe duas bases
independentes no mesmo índice, pois podem conter IDs coincidentes.

`LEGACY_DATABASE_PATH` define a origem; o antigo `DATABASE_PATH` também é aceito
como origem por compatibilidade. Apenas `DJANGO_DATABASE_PATH` define o banco novo.
Mantenha `DOCUMENTS_PATH`, `VECTOR_DB_PATH`, modelo e dimensões de embeddings
coerentes com os usados antes da migração. Se mudar o modelo, crie um novo índice
e reindexe os documentos.

## Cadastros, aulas e documentos

1. Entre em **Administração** e cadastre um **Setor**.
2. Cadastre o **Treinamento**, selecione o setor e marque **Ativo**.
3. Adicione suas **Aulas**, com ordem única dentro do treinamento. Use o editor
   de aulas para incluir a explicação completa. Somente aulas publicadas aparecem
   para o colaborador.
4. Cole o link do arquivo de vídeo do Drive em cada aula. O acesso é controlado
   pelas permissões do Drive e pode exigir a conta Google da empresa.
5. No treinamento, clique em **Gerenciar documentos** e envie o PDF/DOCX autorizado.
6. Aguarde **Indexado**. Em caso de falha, o arquivo permanece pendente para
   reindexação ou exclusão, sem participar das respostas do chat.
   Se o original foi movido ou removido, a tela indica **Arquivo ausente**;
   envie novamente o documento. Materiais ausentes não entram no chat.
7. Abra o treinamento: a lista permite alternar entre as aulas, mantendo os
   materiais e o chat do mesmo treinamento.

São aceitos links HTTPS de arquivo do Drive (`/file/d/<id>/view` ou `/open?id=<id>`),
incluindo `resourcekey`. Pastas e outros provedores são rejeitados. O navegador
reproduz o vídeo pelo player do Drive; há um link para abri-lo em outra aba.

Os documentos são enviados e excluídos pela tela de gerenciamento para manter
banco, arquivos e vetores consistentes. Setores com treinamentos e treinamentos
com documentos não podem ser excluídos diretamente. Remova os documentos pela
ação apropriada primeiro.

## Permissões

Colaboradores autenticados podem acessar todos os treinamentos ativos; ainda
não há matrícula nem restrição por setor. Usuários da equipe só administram os
modelos e ações autorizados por suas permissões ou grupos do Django.

O gerenciamento de documentos exige membro da equipe e as permissões de
visualização, adição, alteração ou exclusão correspondentes à ação.
O Admin de documentos é somente para consulta; o envio e a exclusão ficam na
tela que também atualiza o índice.

## Configuração da IA

Preencha localmente no `.env`:

```dotenv
GOOGLE_API_KEY=
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001
GEMINI_EMBEDDING_DIMENSIONS=768
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openrouter/free
```

Cadastro, login e reprodução de vídeos não exigem chaves de IA. Indexação e
consulta dos documentos precisam das chaves. Reinicie o servidor após mudar o
`.env`. Nunca versione credenciais.

| Variável | Padrão | Uso |
|---|---|---|
| DJANGO_DATABASE_PATH | app/database/platform.sqlite3 | Banco Django |
| LEGACY_DATABASE_PATH | app/database/training.sqlite3 | Origem da importação |
| DOCUMENTS_PATH | media/documentos | Documentos originais |
| VECTOR_DB_PATH | vector_db | Índice Chroma |
| MAX_UPLOAD_MB | 10 | Limite de arquivo |
| HTTP_TIMEOUT_SECONDS | 60 | Timeout dos provedores |
| CHUNK_TOKENS | 1000 | Tamanho aproximado dos trechos |
| CHUNK_OVERLAP_TOKENS | 150 | Sobreposição dos trechos |
| RAG_MAX_DISTANCE | 0.5 | Distância cosseno máxima |

Caminhos relativos são resolvidos a partir da raiz. A interface do colaborador
usa CSS local; a tela de documentos usa Bootstrap via CDN. O Django Admin usa
seus próprios arquivos estáticos.

## Comportamento do RAG

PDF/DOCX → extração com página/seção → divisão em trechos → Gemini Embeddings →
Chroma → recuperação exclusiva por treinamento/documentos indexados →
OpenRouter → resposta com citações e trechos das fontes.

Sem material relevante ou sem citações válidas, o chat informa que não encontrou
a informação. Citações não comprovam fidelidade semântica: confira as respostas
contra os procedimentos reais. O histórico fica no navegador, limitado a 20
mensagens por usuário e treinamento, e não é enviado ao modelo. Cada pergunta
deve ser compreensível sozinha.

São preservadas as validações de MIME, assinatura, nomes e caminhos; documentos
recebem UUID. DOCX é limitado a 50 MB descomprimidos e 2000 entradas, sem macros.
PDF é limitado a 300 páginas, texto a 2 milhões de caracteres e índice a 1000
trechos por documento. PDFs digitalizados precisam de OCR prévio, não implementado.

A operação atual usa um processo local: um lock coordena indexação, exclusão e
consultas. Não há fila de processamento. Falhas de provedores têm mensagens
públicas sem respostas brutas ou credenciais, e não há retries automáticos que
possam duplicar cobranças. Texto e perguntas vão ao Google; trechos recuperados
vão ao OpenRouter.

Faça backup conjunto do banco Django, documentos e índice, além de preservar o
SQLite legado durante a transição. As migrações de esquema usam o Django.
O servidor `runserver` e `DJANGO_DEBUG=true` destinam-se ao desenvolvimento local.

## Validação

```powershell
uv sync --locked --dev
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest -q
uv run python -m compileall -q app config tests
```

A suíte testa autenticação, permissões, CSRF, múltiplas aulas, importação transacional,
PDF/DOCX, reindexação, exclusão, Chroma real e respostas com fontes. As APIs externas
são simuladas e bloqueadas durante os testes. O conteúdo de demonstração é fictício.

Chamadas reais de IA, qualidade das respostas e acesso aos vídeos privados do
Drive exigem validação com as contas e documentos da empresa.
