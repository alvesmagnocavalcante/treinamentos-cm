# Docker e Render

## Demonstração publicada

- Endereço: https://treinamentos-carmel.onrender.com
- Painel: https://dashboard.render.com/web/srv-db96avvbtjjs73fgqh50
- Workspace: Projetos; região: Virginia; plano: Free.
- Repositório: `alvesmagnocavalcante/treinamentos-cm`, branch `main`.
- Deploy automático habilitado: novos pushes em `main` iniciam um build.
- O banco Aiven e os usuários existentes foram mantidos.
- O Drive usa `GOOGLE_SERVICE_ACCOUNT_JSON` nas variáveis protegidas do Render.
- A chave Django é exclusiva da hospedagem; `DJANGO_DEBUG=false`.

As credenciais não estão no código nem na imagem. Para alterá-las, use a seção
Environment do serviço e aguarde o redeploy. O `.env` do computador não é enviado.

## 1. O que a imagem executa

A imagem usa Python 3.12, dependências do `uv.lock`, Gunicorn com um processo e
quatro threads, e WhiteNoise para CSS, JavaScript, fontes e logos. Executa com um
usuário sem privilégios. O build não recebe credenciais nem acessa o banco.

Ao iniciar, aplica as migrações e só então abre o servidor na variável `PORT`
(padrão `10000`). Se a migração falhar, o contêiner encerra com erro.
Mantenha uma instância: as operações de documentos usam um lock por processo.

O módulo `config.production` é selecionado automaticamente pela imagem.
O comando local `uv run python manage.py runserver` mantém a configuração anterior.
Dados e vetores continuam no PostgreSQL/Aiven. Não é necessário disco persistente.

## 2. Executar no computador

1. Construa a imagem na raiz do projeto:

   ```powershell
   docker build -t treinamentos-cm .
   ```

2. Inicie usando o `.env` existente e monte a credencial do Drive como somente leitura:

   ```powershell
   docker run --rm --name treinamentos-cm -p 10000:10000 --env-file .env --env DJANGO_DEBUG=true --env DJANGO_SECRET_KEY=local-container-demo-only --env GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/google-drive.json --mount 'type=bind,source=C:\Users\magno.alves\Downloads\json-drive\n8ngog-472001-e44891b505f5.json,target=/etc/secrets/google-drive.json,readonly' treinamentos-cm
   ```

3. Abra `http://localhost:10000`. Esse comando usa o banco indicado no `.env`,
   incluindo suas migrações; não cria um banco separado. `DJANGO_DEBUG=true` é
   exclusivo deste teste HTTP local. Na hospedagem, use `false` e HTTPS.
   A chave mostrada no comando é fictícia e exclusiva do teste local. No arquivo
   usado por `--env-file`, use valores sem aspas externas: o Docker não interpreta
   esse arquivo da mesma forma que o carregador `.env` do Python.

## 3. Configurar no Render Free

1. Publique os arquivos no repositório e crie um **Web Service** a partir dele.
2. Escolha **Docker**, plano **Free**, Dockerfile `./Dockerfile` e contexto `.`.
   Deixe **Docker Command** vazio para usar o entrypoint da imagem.
3. Em **Environment**, configure:

   | Variável | Valor |
   |---|---|
   | `DATABASE_URL` | URI atual do banco Aiven da aplicação |
   | `DJANGO_DEBUG` | `false` |
   | `DJANGO_SECRET_KEY` | Chave aleatória forte e fixa, exclusiva da hospedagem |
   | `GOOGLE_API_KEY` | Chave atual de embeddings |
   | `OPENROUTER_API_KEY` | Chave atual do OpenRouter |
   | `GEMINI_EMBEDDING_MODEL` | Mesmo modelo usado no índice atual |
   | `GEMINI_EMBEDDING_DIMENSIONS` | Mesmas dimensões do índice atual |
   | `OPENROUTER_MODEL` | Modelo atual de respostas |
   | `GOOGLE_APPLICATION_CREDENTIALS` | `/etc/secrets/google-drive.json` |

4. Adicione um **Secret File** chamado `google-drive.json`, com o conteúdo do JSON
   já usado localmente. A conta mantém o acesso existente à pasta do Drive.
   Se usa `DATABASE_SSL_ROOT_CERT`, adicione a CA como outro Secret File e configure
   o caminho `/etc/secrets/aiven-ca.pem`. Caminhos Windows não existem no Render.
   Alternativamente, configure o conteúdo completo do JSON em
   `GOOGLE_SERVICE_ACCOUNT_JSON`, sem `GOOGLE_APPLICATION_CREDENTIALS`.
   Esta é a opção usada pelo deploy via conector. Quando preenchida, essa variável
   tem prioridade sobre o arquivo/ADC e deve permanecer secreta.
5. Configure o **Health Check Path** como `/conta/entrar/` e inicie o deploy.
6. Teste login, treinamento, vídeo, download, chat e sincronização no endereço HTTPS.

O hostname `.onrender.com`, o proxy HTTPS e a origem CSRF são configurados a partir
de `RENDER_EXTERNAL_HOSTNAME`, fornecido pelo Render. Para domínio próprio, adicione
o host em `DJANGO_ALLOWED_HOSTS` e a origem completa em
`DJANGO_CSRF_TRUSTED_ORIGINS`, separando múltiplos valores por vírgula.

Os administradores e materiais existentes continuam no Aiven; não é necessário
recriar usuários nem reindexar para mudar a hospedagem. Não coloque `.env`, JSON de
conta de serviço ou senhas no Git ou em argumentos de build. O `.dockerignore`
inclui somente os arquivos de aplicação necessários.

O Free pode suspender a aplicação após inatividade e compartilha cotas de uso
com os outros serviços gratuitos do workspace. O primeiro acesso pode demorar;
abra o endereço antes da demonstração. Banco e APIs continuam com seus próprios
limites. Consulte os [limites oficiais](https://render.com/docs/free).

Referências: [Docker no Render](https://render.com/docs/docker) e
[uv em Docker](https://docs.astral.sh/uv/guides/integration/docker/).
