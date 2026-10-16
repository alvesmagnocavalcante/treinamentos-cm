# Manutenção, testes e publicação

[Início](../README.md) · [Configuração](CONFIGURACAO.md) · [Operação](OPERACAO.md) · [Registro](REGISTRO.md)

Este guia é para quem mantém o código, cuida dos dados ou prepara a hospedagem.

## 1. Organização do código

| Caminho | Responsabilidade |
|---|---|
| `config/settings.py` | Configuração do Django, banco, templates, segurança e estáticos |
| `app/config.py` | Leitura e validação das variáveis de ambiente |
| `app/database.py` | Validação da conexão PostgreSQL e exigência de TLS remoto |
| `app/models.py` | Setores, treinamentos, aulas, documentos e trechos com vetores |
| `app/migrations/` | Evolução versionada das tabelas e ativação de `vector` |
| `app/admin.py`, `app/admin_site.py` | Cadastros e painel administrativo |
| `app/views/` | Autenticação/permissões por ação, requisições e respostas HTTP |
| `app/services/drive.py` | Autenticação, listagem, download e exportação do Drive |
| `app/services/drive_sync.py` | Sincronização por treinamento e detecção de versões |
| `app/services/document_files.py` | Leitura da origem Drive ou do arquivo guardado no banco |
| `app/services/documents.py` | Cadastro, extração, indexação e exclusão coordenadas |
| `app/services/ingest.py`, `chunking.py` | Validação do arquivo, extração de texto e divisão em trechos |
| `app/services/embeddings.py`, `llm.py`, `http.py` | Clientes de IA e tratamento seguro de erros |
| `app/services/vector_store.py` | Gravação e busca vetorial com PostgreSQL/pgvector |
| `app/services/rag.py` | Recuperação, prompt, validação de citações e resposta pública |
| `app/services/video.py` | Validação dos links e transmissão do vídeo em blocos |
| `app/runtime.py` | Composição dos serviços e lock local das operações com documentos |
| `app/templates/`, `app/static/` | Telas, comportamento no navegador e identidade visual |
| `config/test_settings.py`, `tests/` | Ambiente isolado e testes automatizados |

As views cuidam de HTTP e permissões; os serviços fazem o processamento. Os
serviços recebem as dependências necessárias, permitindo testar sem chamar IA real.
Os templates de colaboradores usam Jinja; o Django Admin mantém seus templates Django.

## 2. Estrutura dos dados e fluxo do RAG

Relações principais: **Setor → Treinamento → Aulas e Documentos → Trechos**.
Usuários, grupos, permissões e sessões usam as tabelas padrão do Django.

`DocumentoTrecho` guarda texto, ordem, página/seção, embedding, modelo e dimensão.
Os dados do documento informam o treinamento a que os trechos pertencem. Há uma
restrição para não duplicar o mesmo ID do Drive dentro do mesmo treinamento.

### Durante a indexação

1. A aplicação valida e lê o arquivo; no Drive, a cópia é temporária no PostgreSQL.
2. Extrai texto, páginas de PDF e seções de DOCX.
3. Divide o texto em trechos com sobreposição, preservando páginas/seções.
4. Envia lotes de até 32 trechos à Gemini API com finalidade `RETRIEVAL_DOCUMENT`.
5. Valida dimensões, números finitos e normaliza os vetores.
6. Substitui os trechos do documento no PostgreSQL em uma transação e marca o
   documento como indexado após a conclusão.

Enquanto um documento está pendente, ele fica excluído das consultas. A substituição
vetorial usa transação e bloqueio da linha do documento. Uma falha não libera
um conjunto parcial de novos trechos para o chat.

### Durante uma pergunta

1. Confere login, treinamento ativo e pergunta em JSON, com até 2000 caracteres.
2. Seleciona documentos indexados e disponíveis do treinamento.
3. Gera o embedding da pergunta com finalidade `RETRIEVAL_QUERY`.
4. Faz busca exata por distância de cosseno e recupera até 15 trechos.
5. Filtra por distância máxima, treinamento e IDs de documentos permitidos.
6. Envia pergunta e contexto ao OpenRouter. O modelo recebe temperatura 0 e limite
   de saída de 1500 tokens; uma saída truncada é rejeitada.
7. Valida os IDs de referência e remove citações/rodapés da resposta exibida.

A comparação é exata no PostgreSQL atual: não foi criado índice aproximado HNSW.
Se a base crescer, meça latência, armazenamento e consumo de CPU antes de mudar
a estratégia. O modelo/dimensão ficam associados aos trechos para impedir
consultas com vetores incompatíveis.

### Onde ficam os arquivos

| Conteúdo | Armazenamento |
|---|---|
| Usuários, sessões e cadastros | PostgreSQL |
| Trechos e embeddings | PostgreSQL/pgvector |
| Original do Drive | No Drive; cópia apenas temporária |
| Upload manual | Binário no PostgreSQL; temporário durante a leitura |
| Vídeo | No Drive, retransmitido sem salvar o arquivo inteiro |
| Histórico do chat | Sessão da aba do navegador, até 20 mensagens |
| Preferência de tema | `localStorage` do navegador |

O RAG já indexado pode responder sem reler o Drive a cada pergunta. Por isso, a
revogação de acesso ou remoção do original exige revisão/exclusão também na aplicação.
Download e reindexação dependem do acesso atual ao original do Drive.

## 3. Atualizar o projeto

1. Faça backup antes de mudanças de esquema ou alterações importantes.
2. Atualize o código pela rotina de versionamento da equipe.
3. Execute na raiz:

   ```powershell
   uv sync --locked
   uv run python manage.py migrate
   uv run python manage.py check
   ```

4. Reinicie o servidor e confira login, painel, uma aula e uma pergunta conhecida.

`migrate` aplica mudanças já versionadas. `makemigrations` é usado pelo desenvolvedor
quando ele altera os modelos, com revisão do arquivo gerado antes de aplicá-lo.
Não apague migrações para tentar resolver um erro de conexão ou permissão.

## 4. Testes e verificações

### Verificação padrão

```powershell
uv sync --locked --dev
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python -m compileall -q app config tests
git diff --check
```

`manage.py check` usa a configuração da aplicação. Já o `pytest` usa
`config.test_settings`, que não aceita por acidente a `DATABASE_URL` do `.env`.
Sem `TEST_DATABASE_URL`, os testes usam o PostgreSQL descartável em
`127.0.0.1:55439`, descrito abaixo. Todo teste de banco usa PostgreSQL real;
não existe fallback SQLite nem grupo pulado por tipo de banco. Chamadas externas
HTTP dos provedores são bloqueadas e simuladas, portanto não comprovam a cota,
disponibilidade nem a qualidade atual do modelo real.

### PostgreSQL/pgvector real em contêiner descartável

Requer Docker em execução. Use este banco só para testes: a suíte cria e remove
um banco de teste. A senha abaixo é fictícia e a porta fica restrita ao computador.

```powershell
docker run --detach --name carmel-pgvector-tests --publish 127.0.0.1:55439:5432 --env POSTGRES_USER=training_test --env POSTGRES_PASSWORD=local-test-only --env POSTGRES_DB=training_test pgvector/pgvector:pg17
docker exec carmel-pgvector-tests pg_isready -U training_test -d training_test
```

Espere o comando informar que está aceitando conexões. Se ainda não estiver
pronto, repita apenas a verificação `pg_isready`. Depois:

```powershell
$env:TEST_DATABASE_URL = 'postgresql://training_test:local-test-only@127.0.0.1:55439/training_test?sslmode=disable'
uv run pytest -q
Remove-Item Env:TEST_DATABASE_URL
docker rm --force --volumes carmel-pgvector-tests
```

O último comando remove somente esse contêiner descartável e seus volumes.
Não substitua a URI de teste pela conexão do Aiven em uso. A exceção sem TLS vale
para loopback local, não para o banco remoto.

O número de testes foi revisado na limpeza: cenários exclusivos de SQLite,
Chroma e importação antiga foram removidos. A validação inclui a proteção da
migração que retira o campo de caminho local, além de todos os fluxos atuais.

## 5. Backup e recuperação

O Drive e o PostgreSQL protegem partes diferentes do sistema. Guardar os PDFs
não preserva usuários, permissões, aulas e configurações de treinamento.

1. Faça backup do banco `treinamentos`, incluindo dados e trechos vetoriais.
2. Preserve os originais do Drive e as permissões necessárias de acesso.
3. Guarde separadamente configurações e credenciais em um local seguro.
4. Teste uma restauração em **outro banco**, sem sobrescrever o ambiente em uso.
5. Confira login, cadastros, documentos, contagem de trechos e uma pergunta conhecida.

Para backup lógico, use `pg_dump`/`pg_restore` compatíveis com a versão do servidor
ou uma ferramenta de administração PostgreSQL. Exemplo de backup manual, com
senha solicitada interativamente, usando ferramentas PostgreSQL instaladas:

```powershell
New-Item -ItemType Directory -Path .secrets -Force | Out-Null
$env:PGSSLMODE = 'require'
pg_dump --host=HOST --port=PORTA --username=USUARIO --dbname=treinamentos --format=custom --file=.secrets/backup-treinamentos.dump --password
Remove-Item Env:PGSSLMODE
```

Substitua os campos em maiúsculas. Se usar CA, configure também `PGSSLROOTCERT`
e `PGSSLMODE=verify-full`. O arquivo gerado contém dados internos: mantenha-o fora
do Git e da pasta pública da aplicação. Para restaurar, prepare um banco separado
com a extensão `vector` e use `pg_restore` conforme as permissões desse ambiente.

Sem backup do índice, os arquivos do Drive podem ser reindexados, com consumo
das APIs. Isso não recria usuários, aulas e permissões perdidos.

## 6. Preparação para publicar no Render

**Status desta implementação: banco remoto funcionando; publicação não executada.**
O projeto ainda não contém a preparação completa de execução em produção:
Gunicorn/WhiteNoise não estão nas dependências e não há configuração de deploy
finalizada. Não use `runserver` como comando de produção.

### Configurações já compatíveis

O banco e os arquivos temporários já permitem que os dados persistentes fiquem
fora da instância. Configure no serviço Render:

| Configuração | Valor/origem |
|---|---|
| `DATABASE_URL` | URI completa do banco `treinamentos` no Aiven |
| `GOOGLE_APPLICATION_CREDENTIALS` | `/etc/secrets/google-drive.json` |
| Secret File `google-drive.json` | Conteúdo do JSON da conta de serviço |
| `DATABASE_SSL_ROOT_CERT` | Opcional: `/etc/secrets/aiven-ca.pem` com a CA como Secret File |
| `GOOGLE_API_KEY` | Chave de embeddings |
| `OPENROUTER_API_KEY` | Chave do OpenRouter |
| Modelos e dimensões | Mesmos valores compatíveis com os documentos já indexados |
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECRET_KEY` | Valor forte, fixo e secreto, exclusivo do ambiente |
| `DJANGO_ALLOWED_HOSTS` | Host `SEU-SERVICO.onrender.com` e domínio próprio, se houver |

O Render disponibiliza Secret Files em `/etc/secrets/NOME_DO_ARQUIVO`.
Não envie o JSON ao Git e não copie o caminho Windows para o servidor.
[Configuração oficial de variáveis e arquivos secretos](https://render.com/docs/configure-environment-variables).

### Trabalho que falta antes de publicar

1. Adicionar/configurar um servidor WSGI de produção, como Gunicorn, usando
   `config.wsgi:application` e a porta `$PORT` da hospedagem.
2. Configurar distribuição dos estáticos, por exemplo WhiteNoise, e `collectstatic`.
   Esse comando sozinho não faz o servidor entregar CSS, fontes e JavaScript.
3. Definir e validar os comandos de build, migração e início do serviço.
4. Configurar HTTPS/proxy e verificar cookies, login, logout e CSRF no domínio real.
   Não há variável `DJANGO_CSRF_TRUSTED_ORIGINS` implementada neste projeto; se
   precisar dela, será necessário adicionar a configuração ao Django.
5. Começar com um processo da aplicação e validar memória, concorrência, limite
   de conexões e duração das sincronizações. O lock atual é por processo, não é
   um coordenador entre múltiplas instâncias.
6. Verificar backup, credenciais, acesso ao Drive e um fluxo real de chat no deploy.

O [guia oficial de Django no Render](https://render.com/docs/deploy-django)
descreve a preparação de estáticos e inicialização. A criação de outro banco no
Render não é necessária se a aplicação continuar usando o Aiven configurado.

Não é necessário disco persistente para os documentos e o índice no modo
PostgreSQL atual. Isso não significa hospedagem sem limites ou sem custos:
há consumo de memória temporária, banco, APIs e tráfego, inclusive do vídeo.

No Cloud Run, o mesmo banco externo pode ser usado, mas credenciais, contêiner,
porta e configuração de produção também precisam ser preparados. Não houve
deploy no Cloud Run durante esta implementação.

## 7. Limites atuais e cuidados ao evoluir

- Sem fila de processamento, agendamento de sincronização ou tarefas em segundo plano.
- Sem restrição de acesso por setor ou matrícula individual.
- Sem OCR, transcrição de vídeos ou indexação automática do texto das aulas.
- Sem coordenador de operações de documentos entre diferentes processos/instâncias.
- Sem histórico de chat centralizado nem envio da conversa inteira ao modelo.
- Sem repetição automática de chamadas pagas de IA no adaptador HTTP. O cliente
  de autenticação do Google pode renovar tokens; isso é diferente de repetir uma
  indexação inteira.

As mensagens públicas dos serviços omitem respostas brutas e credenciais.
Mantenha `DEBUG=false` em produção: erros não tratados não devem expor a tela
de diagnóstico de desenvolvimento.
