# Configuração do projeto

[Início](../README.md) · [Operação](OPERACAO.md) · [Manutenção](MANUTENCAO.md) · [Registro](REGISTRO.md)

Este guia explica como reproduzir a configuração. Para apenas abrir o ambiente
já configurado, siga **Rodar neste computador** no README.

## 1. O papel de cada serviço

| Serviço ou arquivo | Para que serve | O que não substitui |
|---|---|---|
| Django | Login, painel, aulas, documentos e chat | Não é um serviço de IA |
| Aiven PostgreSQL | Usuários, sessões, treinamentos, documentos e trechos | Não guarda os vídeos do Drive |
| Extensão `pgvector` | Guarda embeddings e calcula semelhança entre textos | Não gera os embeddings |
| Google Drive | Guarda os documentos originais e os vídeos | Não é o banco de usuários nem o índice do RAG |
| Gemini API | Transforma trechos e perguntas em embeddings | Não redige as respostas nesta aplicação |
| OpenRouter | Encaminha contexto e pergunta ao modelo que redige a resposta | Não lê a pasta do Drive sozinho |
| `.env` | Guarda configurações específicas deste ambiente | Não deve ser enviado ao Git |
| JSON da conta de serviço | Identifica a aplicação para ler o Drive | Não substitui a chave da Gemini API |

RAG é o processo de buscar informações nos materiais antes de pedir uma resposta
à IA. Embeddings são listas de números que permitem comparar o significado dos textos.

## 2. Preparar uma instalação nova

Pré-requisitos: Python 3.12, `uv`, acesso ao projeto e conexão à internet.
As versões das dependências estão fixadas em `uv.lock`.

1. Abra o PowerShell na raiz do projeto, onde está `manage.py`.
2. Instale as dependências:

   ```powershell
   uv sync --locked
   ```

3. Crie o `.env` somente se ele ainda não existir:

   ```powershell
   if (-not (Test-Path -LiteralPath .env)) {
       Copy-Item -LiteralPath .env.example -Destination .env
   }
   ```

4. Configure o banco, as credenciais do Drive e as chaves conforme as seções abaixo.
5. Com o banco escolhido, crie o esquema e seu administrador:

   ```powershell
   uv run python manage.py migrate
   uv run python manage.py createsuperuser
   ```

6. Se ainda não houver setor e treinamento, use o assistente inicial:

   ```powershell
   uv run python manage.py setup_training --drive-folder "https://drive.google.com/drive/folders/ID_DA_PASTA"
   ```

   Esse comando cria RH e Integração, ou completa o vínculo da pasta se o cadastro
   já existir sem pasta. Não duplica o mesmo cadastro nem troca outra pasta existente.
   Também aceita `--setor "Recepção" --titulo "Atendimento"`. Não cria aulas nem usuários.

7. Inicie o sistema:

   ```powershell
   uv run python manage.py runserver 127.0.0.1:8765
   ```

`migrate` cria ou atualiza **a estrutura das tabelas**. Ele não importa os dados
do SQLite nem do Chroma. Não execute `makemigrations` para uma instalação normal;
as migrações necessárias já acompanham o projeto.

## 3. Banco novo no Aiven

### O que foi configurado neste ambiente

Foi criado um banco separado chamado `treinamentos`, no serviço PostgreSQL
informado pelo responsável. O banco anterior desse serviço e o SQLite local
foram preservados. A aplicação passou a usar a conexão do novo banco no `.env`.

### Como repetir em outro ambiente

1. Crie ou selecione um serviço **PostgreSQL** no Aiven.
2. Crie um banco dedicado à aplicação, chamado `treinamentos`. Se ele já existir,
   não o exclua nem o recrie. A conta usada precisa ter as permissões necessárias.
3. Copie a URI de conexão completa do painel, com usuário e senha revelados.
   `CLICK_TO:REVEAL_PASSWORD` é um marcador da interface, não uma senha válida.
4. Confira se a parte após a porta aponta para `/treinamentos`, e não para outro banco.
5. Salve a URI apenas no `.env`:

   ```dotenv
   DATABASE_URL='postgres://USUARIO:SENHA_CODIFICADA@HOST:PORTA/treinamentos?sslmode=require'
   ```

6. Execute `uv run python manage.py migrate`. Além das tabelas, a migração habilita
   a extensão `vector`, usada pelo `pgvector`. Se houver erro de permissão, corrija
   o usuário/permissões no Aiven antes de tentar novamente.

Caracteres especiais da senha precisam estar codificados para uma URL. Prefira
copiar a URI completa fornecida pelo painel. Nunca publique a conexão real no
README, no `.env.example`, em capturas de tela ou no código.

### TLS e certificado

TLS protege a conexão entre aplicação e banco. A configuração aceita conexões
remotas com `require`, `verify-ca` ou `verify-full`; não aceita desativar TLS para
um host remoto.

`sslmode=require` exige criptografia, mas não verifica a identidade do servidor.
Para verificar também essa identidade, baixe a CA do projeto Aiven e informe:

```dotenv
DATABASE_SSL_ROOT_CERT='C:/caminho/seguro/aiven-ca.pem'
```

Ao preencher essa variável, a aplicação utiliza `sslmode=verify-full`. O arquivo
de certificado precisa existir na máquina ou hospedagem que executa o Django.
[Referência de certificados do Aiven](https://aiven.io/docs/platform/concepts/tls-ssl-certificates).

### Capacidade e conexões

O projeto encerra as conexões ao fim de cada requisição (`CONN_MAX_AGE=0`) e usa
timeout de conexão de 10 segundos. Isso evita manter muitas conexões ociosas,
mas não impede que muitos acessos simultâneos atinjam a cota do serviço.

Na documentação consultada em 16/10/2026, o plano gratuito tinha 1 GB de disco,
1 GB de RAM e limite de 20 conexões, sem SLA. Verifique as condições do seu plano
antes de publicar. Textos, vetores e arquivos enviados manualmente consomem esse
espaço. [Limites oficiais](https://aiven.io/docs/products/postgresql/concepts/pg-free-tier).

## 4. Google Drive privado

### Criar e autorizar a conta de serviço

1. No Google Cloud, selecione o projeto e habilite a **Google Drive API**.
2. Em **IAM e administrador → Contas de serviço**, crie uma conta para a aplicação.
3. Copie o e-mail dessa conta, semelhante a
   `treinamentos@SEU-PROJETO.iam.gserviceaccount.com`.
4. No Drive, compartilhe a pasta de documentos com esse e-mail como **Leitor**.
5. Para execução local, gere uma chave JSON da conta de serviço e guarde-a em um
   local protegido. A pasta não precisa ser pública nem conceder edição por link.

Compartilhar a pasta e configurar a credencial são duas etapas diferentes.
Uma concede acesso; a outra permite que o programa se identifique. Dar funções
no IAM do Google Cloud também não compartilha automaticamente uma pasta do Drive.
[Credenciais e compartilhamento](https://developers.google.com/workspace/guides/create-credentials#service-account).

### Informar o JSON no computador

No `.env`, informe o caminho para o **arquivo completo**, incluindo `.json`:

```dotenv
GOOGLE_APPLICATION_CREDENTIALS='C:/caminho/seguro/google-drive.json'
```

No Windows, use barras `/`, como acima, para evitar que sequências como `\n`
sejam interpretadas dentro de valores com aspas duplas. O caminho antigo de um
computador não funciona automaticamente em outro.

Nesta instalação, a credencial foi mantida em uma pasta local fora do código.
Também pode ser guardada em `.secrets/`, diretório ignorado pelo Git. O conteúdo
do JSON não deve ser colado no `.env`, no chat ou em documentação versionada.

O cliente utiliza credenciais padrão do Google (ADC), com escopo
`https://www.googleapis.com/auth/drive.readonly`. Esse escopo é apenas de leitura:
a aplicação não modifica nem apaga arquivos na origem. Em uma hospedagem, a
credencial e o acesso ao Drive também precisam ser configurados no servidor.

### Vincular a pasta

1. Entre no Admin e abra **Treinamentos → Gerenciar documentos**.
2. Cole o link da pasta no campo **Pasta do Google Drive**.
3. Clique em **Sincronizar e indexar**.
4. Aguarde o status **Indexado** e faça uma pergunta de verificação.

Formatos aceitos para esse campo:

```text
https://drive.google.com/drive/folders/ID_DA_PASTA
https://drive.google.com/drive/folders/ID_DA_PASTA?usp=sharing
ID_DA_PASTA
```

No editor do treinamento, prefira o link HTTPS completo. O vínculo fica salvo
no PostgreSQL; não é necessário adicionar a pasta ao `.env`.

## 5. Chaves e modelos de inteligência artificial

As duas chaves têm funções distintas:

```dotenv
GOOGLE_API_KEY='SUA_CHAVE_DE_EMBEDDINGS'
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001
GEMINI_EMBEDDING_DIMENSIONS=768
OPENROUTER_API_KEY='SUA_CHAVE_OPENROUTER'
OPENROUTER_MODEL=openrouter/free
```

O último valor acima é o **padrão do projeto**. No ambiente conferido em
16/10/2026, `OPENROUTER_MODEL` estava configurado como
`nvidia/nemotron-3.5-super-vl:free`. O `.env` determina o modelo efetivamente usado.
Este registro não garante que um modelo gratuito continue disponível no futuro.

Ao indexar, o texto extraído vai para o Google. Ao perguntar, a pergunta também
vai para o Google para gerar seu embedding; a pergunta e os trechos recuperados
vão ao OpenRouter e ao provedor do modelo selecionado.

O plano de hospedagem não inclui automaticamente a cota dessas APIs. Limites da
Gemini API variam por projeto/modelo e devem ser verificados no AI Studio.
[Limites oficiais da Gemini API](https://ai.google.dev/gemini-api/docs/rate-limits).

Trocar apenas o modelo de respostas não exige recalcular os embeddings. Trocar
o modelo de embeddings ou suas dimensões exige reindexar os documentos. Não
misture vetores de modelos diferentes no mesmo treinamento.

## 6. Todas as variáveis de configuração

Valores abaixo são padrões do código ou exemplos, não credenciais reais.

| Variável | Padrão | O que controla |
|---|---|---|
| `DATABASE_URL` | Obrigatória | Conexão PostgreSQL; sem ela a aplicação informa erro de configuração |
| `DATABASE_SSL_ROOT_CERT` | Vazio | Caminho da CA; ativa verificação TLS completa |
| `GOOGLE_APPLICATION_CREDENTIALS` | Sem valor obrigatório no código | Caminho do JSON/credencial ADC para o Drive |
| `GOOGLE_API_KEY` | Vazio | Acesso à API de embeddings do Google |
| `GEMINI_EMBEDDING_MODEL` | `models/gemini-embedding-001` | Modelo que gera os vetores |
| `GEMINI_EMBEDDING_DIMENSIONS` | `768` | Quantidade de números por embedding |
| `OPENROUTER_API_KEY` | Vazio | Acesso à API que gera as respostas |
| `OPENROUTER_MODEL` | `openrouter/free` | Modelo ou roteador usado nas respostas |
| `DJANGO_DEBUG` | `true` | Modo de desenvolvimento; deve ser `false` em produção |
| `DJANGO_SECRET_KEY` | Vazio | Assinaturas e segurança do Django; obrigatória em produção |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Hosts aceitos, separados por vírgulas, sem `https://` ou caminhos |
| `HTTP_TIMEOUT_SECONDS` | `60` | Timeout das chamadas de IA e do cliente do Drive |
| `MAX_UPLOAD_MB` | `10` | Limite por documento, em unidades de 1024 × 1024 bytes |
| `CHUNK_TOKENS` | `1000` | Tamanho aproximado de cada trecho de texto |
| `CHUNK_OVERLAP_TOKENS` | `150` | Parte repetida entre trechos para preservar contexto |
| `RAG_MAX_DISTANCE` | `0.5` | Distância máxima para aceitar trechos; menor é mais restritivo |
| `TEST_DATABASE_URL` | URI local em `127.0.0.1:55439` | Conexão com o PostgreSQL descartável de testes; nunca usa a conexão do `.env` automaticamente |

Os trechos usam a estimativa de quatro caracteres por token, não uma contagem
exata do provedor. A sobreposição precisa ser menor que o tamanho do trecho;
o tamanho configurado deve ser de até 2000 tokens aproximados.

Variáveis já definidas no processo têm prioridade sobre o `.env`. Se a aplicação
ignorar uma mudança, confira também o terminal, o serviço e o painel da hospedagem.
Reinicie o servidor após qualquer alteração de configuração.

## 7. Segurança da execução local

Em desenvolvimento, se `DJANGO_SECRET_KEY` estiver vazia, o projeto gera uma chave
em `.cache/django-secret`. Isso evita trocar sessões a cada reinício local.
Na hospedagem, configure uma chave fixa e secreta no ambiente; não dependa desse
arquivo temporário. Com `DJANGO_DEBUG=false`, os cookies de sessão e CSRF exigem HTTPS.

O projeto utiliza somente PostgreSQL e `pgvector`. O importador e os caminhos de
armazenamento legados foram retirados. Os dados locais anteriores foram arquivados
em `.archive/`, ignorado pelo Git, para recuperação manual se necessário.
