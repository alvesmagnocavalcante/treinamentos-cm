# Carmel Hotéis · Treinamentos

Plataforma Django para treinamentos internos. O colaborador entra com seu usuário,
seleciona um treinamento, acompanha suas aulas, consulta materiais e tira dúvidas
no chat com RAG. A administração usa o Django Admin.

Cada treinamento pode ter várias aulas, ordenadas, com vídeo opcional do Google
Drive e explicação em texto. Os documentos PDF/DOCX pertencem ao treinamento e
alimentam o RAG. Vídeos e textos das aulas não são indexados automaticamente.
A geração de roteiros foi retirada por enquanto; não há integração com HeyGen ou n8n.

## Organização do código

O visual segue o guia de marca da Carmel Hotéis: logotipo oficial, cores da
Rede, Plus Jakarta Sans e Timeless. Os arquivos utilizados ficam em
`app/static/brand/`; não há dependência de serviços externos de fontes.
O botão de sol/lua alterna o tema claro e escuro. A preferência é salva no
navegador e compartilhada com o Django Admin; sem escolha prévia, acompanha
o tema do sistema. Os ícones de áudio do vídeo indicam som ativo ou silenciado.

- `config/`: configuração do Django, URLs principais e inicialização.
- `app/models.py`, `forms.py` e `admin.py`: dados, validação de formulários e administração.
- `app/views/training.py`: catálogo e aulas; `chat.py`: perguntas; `documents.py`: gestão e download de documentos.
- `app/services/`: upload, extração, indexação, recuperação e clientes dos provedores de IA.
- `app/runtime.py`: composição dos serviços e lock das operações com documentos.
- `app/templates/` e `app/static/`: interface e recursos do navegador.
- `tests/`: testes de domínio, permissões e integração com provedores simulados.

As views tratam HTTP e permissões; os serviços executam o processamento.
O upload remove o arquivo se a criação do registro falhar. Se a indexação
falhar após o cadastro, mantém o documento pendente para nova tentativa.
Não é necessário adicionar uma camada de repositórios sobre o ORM do Django.

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

O painel em `/admin/` mostra indicadores de setores, treinamentos, aulas e
documentos, além de busca por título/setor e filtro de treinamentos ativos ou
inativos. Use os atalhos para cadastrar usuários, editar treinamentos e aulas
ou gerenciar documentos. Os indicadores e ações respeitam as permissões do
usuário; o link **Administração** aparece no cabeçalho apenas para a equipe.

O login é obrigatório. Não há contas ou senhas padrão. O superusuário é criado
pelo comando interativo acima. Crie os colaboradores em **Usuários** no Admin,
sem marcar **Membro da equipe** ou **Superusuário**.

No celular e em tablets até 1000 px, o treinamento usa as abas **Conteúdo**
e **Assistente**. O chat se ajusta à área visível quando o teclado abre; Enter
insere uma nova linha e o botão de envio manda a pergunta. No computador,
conteúdo e chat aparecem lado a lado e Enter envia. A troca de abas preserva
a conversa e o texto que está sendo digitado.

Em desenvolvimento, se `DJANGO_SECRET_KEY` estiver vazio, uma chave aleatória
persistente é criada em `.cache/django-secret`, ignorada pelo Git. Fora do
ambiente local, configure explicitamente a chave, os hosts permitidos e HTTPS.

## Documentos do Google Drive

Em **Administração → Treinamentos → Gerenciar documentos**, informe o link da
pasta e clique em **Sincronizar e indexar**. A pasta fica vinculada ao treinamento.
Também é possível configurá-la ao editar o treinamento no Django Admin.

Antes da primeira sincronização:

1. Habilite a **Google Drive API** no projeto Google Cloud.
2. Crie uma conta de serviço e compartilhe a pasta do Drive com o e-mail dessa
   conta, com permissão de **Leitor**. Os arquivos não precisam ser públicos.
3. Para execução local, guarde o JSON da conta de serviço em um local seguro
   (por exemplo, `.secrets/google-drive.json`, ignorado pelo Git) e configure
   `GOOGLE_APPLICATION_CREDENTIALS` no `.env` com o caminho absoluto do arquivo.
   Não envie o JSON pelo navegador nem o inclua no repositório. A chave
   `GOOGLE_API_KEY` dos embeddings não substitui essa credencial.
4. Execute `uv sync --locked`, `uv run python manage.py migrate` e reinicie o
   servidor após configurar a credencial.

A integração utiliza as credenciais padrão do Google (ADC), com escopo
`drive.readonly`. A identidade precisa estar autorizada a ler o Drive; no GCP,
configure essa identidade/credencial no ambiente, sem empacotar chaves na imagem.

São importados PDF, DOCX e documentos nativos do Google Docs (exportados em DOCX).
São aceitos até 100 documentos diretamente na pasta, incluindo pastas de drives
compartilhados, respeitando o limite `MAX_UPLOAD_MB` por arquivo. Subpastas,
atalhos, planilhas e apresentações não são importados. PDFs digitalizados
continuam exigindo OCR prévio.

A sincronização é manual. Repita após editar os arquivos: somente documentos
novos, alterados, pendentes ou sem cópia local são baixados e indexados. O mesmo
arquivo não duplica registros no treinamento. Uma falha pode deixar os arquivos
já importados disponíveis e o documento com erro pendente; corrija a causa e
sincronize novamente para retomar. O texto extraído é enviado ao provedor de
embeddings, como ocorre no upload.

Remover um arquivo do Drive ou trocar a pasta não exclui documentos importados:
use **Excluir** na administração para retirar o documento e seus vetores. O botão
**Reindexar** continua processando a cópia local; para buscar a versão mais recente
da origem, use **Sincronizar e indexar**. Nenhum arquivo ou permissão é alterado
no Drive.

Os arquivos baixados continuam em `DOCUMENTS_PATH`, os vetores no Chroma local e
os dados no SQLite. Esta integração não modifica a persistência para Cloud Run.

Referências: [listagem de arquivos](https://developers.google.com/workspace/drive/api/reference/rest/v3/files/list),
[download e exportação](https://developers.google.com/workspace/drive/api/guides/manage-downloads)
e [credenciais ADC](https://google-auth.readthedocs.io/en/latest/reference/google.auth.html).

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
incluindo `resourcekey`. Pastas e outros provedores são rejeitados. O vídeo usa
um player próprio com controles abaixo da imagem, sem sobreposição durante a
reprodução normal. O servidor retransmite o arquivo do Drive em blocos e aceita
requisições por intervalo para avançar e voltar; não guarda o vídeo inteiro em
memória nem o salva em disco. Esse tráfego passa pelo servidor da plataforma.

A transmissão exige login na plataforma e uma aula publicada em treinamento
ativo. O arquivo também precisa permitir leitura sem uma sessão Google no
servidor. O sistema não altera as permissões do Drive nem contorna login ou
bloqueios de download. Para arquivos que exigem conta Google ou ficam
indisponíveis, o link **Abrir vídeo** continua disponível. Sem JavaScript, são
usados os controles nativos do navegador; a tela cheia no iOS também pode usar
os controles do sistema.

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
OpenRouter → validação interna das citações → resposta em linguagem natural.

O assistente usa um tom amigável e direto, mantendo as regras dos materiais.
Referências, nomes de arquivos e rodapés de fontes não aparecem na conversa.
As citações continuam sendo validadas antes de liberar a resposta.

Sem material relevante ou sem citações válidas, o chat informa que não encontrou
a informação. A busca recupera até 15 trechos, mantendo o filtro de distância e
o isolamento por treinamento. Isso permite encontrar páginas de conteúdo que
aparecem depois de capas e sumários na busca semântica.
Sem documentos indexados e com arquivo disponível, o chat informa que os
materiais precisam ter sua indexação verificada (HTTP 409). O status do material
também aparece na área do colaborador.
Citações não comprovam fidelidade semântica: confira as respostas
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
