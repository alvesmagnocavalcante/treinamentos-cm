# Carmel Hotéis · Treinamentos

Plataforma de treinamentos internos com aulas, vídeos do Google Drive, materiais
de apoio e um assistente que responde com base nos documentos de cada treinamento.
O projeto usa Django, PostgreSQL no Aiven e `pgvector` para o RAG.

## Comece por aqui

| O que você precisa fazer | Onde consultar |
|---|---|
| Rodar o projeto, configurar o banco, o Drive e as chaves | [Configuração](docs/CONFIGURACAO.md) |
| Cadastrar usuários e aulas, atualizar documentos ou resolver um erro | [Operação e solução de problemas](docs/OPERACAO.md) |
| Entender o código, testar, fazer backup e preparar a publicação | [Manutenção e publicação](docs/MANUTENCAO.md) |
| Consultar o que foi alterado e validado nesta implementação | [Registro das configurações e melhorias](docs/REGISTRO.md) |

Os guias explicam os termos técnicos na primeira utilização. Exemplos de conexão
contêm valores fictícios; senhas e chaves reais ficam somente no `.env`, em arquivos
protegidos ou no painel da hospedagem.

## Rodar neste computador

A configuração atual já existe no `.env`. Não copie o arquivo de exemplo por cima
dele e não crie outro banco para iniciar o sistema.

1. Abra um terminal PowerShell na pasta do projeto.
2. Instale as dependências e verifique a aplicação:

   ```powershell
   uv sync --locked
   uv run python manage.py check
   ```

3. Inicie o servidor de desenvolvimento:

   ```powershell
   uv run python manage.py runserver 127.0.0.1:8765
   ```

4. Abra o endereço desejado:

   | Área | Endereço |
   |---|---|
   | Treinamentos | http://127.0.0.1:8765/ |
   | Administração | http://127.0.0.1:8765/admin/ |
   | Login | http://127.0.0.1:8765/conta/entrar/ |

Use `Ctrl+C` no terminal para parar. Reinicie o servidor após mudar o `.env`.
`runserver` serve para desenvolvimento; a preparação para hospedagem está no
[guia de manutenção](docs/MANUTENCAO.md).

## Configuração em uso

Registro conferido em **16/10/2026**, horário de Brasília:

| Componente | Configuração |
|---|---|
| Banco da aplicação | PostgreSQL no Aiven, banco separado `treinamentos` |
| Busca do RAG | `pgvector`, distância de cosseno |
| Origem dos documentos | Pasta do Drive vinculada ao treinamento Integração |
| Embeddings | Google, `models/gemini-embedding-001`, 768 dimensões |
| Respostas do chat | OpenRouter; modelo configurado no ambiente |
| Uso no celular | Abas Conteúdo e Assistente, controles de vídeo abaixo da imagem |
| Identidade visual | Marca Carmel, fontes locais e modos claro/escuro |

O banco foi criado do zero. Os dados dos bancos anteriores não foram importados.
A aplicação é executada localmente, mas acessa o Aiven e as APIs pela internet.

## Acesso do administrador

Na criação deste ambiente foi gerado um administrador com senha aleatória.
As credenciais iniciais estão somente no arquivo local
`.secrets/primeiro-acesso-aiven.txt`, ignorado pelo Git. Não existe uma senha
padrão no código. Em outra instalação, crie seu próprio usuário com
`uv run python manage.py createsuperuser`.

Depois de alterar a senha, o arquivo de primeiro acesso deixa de representar a
senha atual. O [guia de operação](docs/OPERACAO.md) explica a recuperação de acesso.

## Como o assistente recebe os materiais

1. O administrador coloca os documentos na pasta do Drive.
2. Em **Gerenciar documentos**, clica em **Sincronizar e indexar**.
3. A aplicação extrai o texto e gera os embeddings, que são representações numéricas
   usadas para encontrar trechos relacionados à pergunta.
4. Textos e embeddings ficam no PostgreSQL. As cópias temporárias do Drive são removidas.
5. A cada pergunta, o sistema busca os trechos do treinamento e solicita uma resposta
   ao modelo de linguagem pelo OpenRouter.

A sincronização é manual. Vídeos e explicações das aulas não alimentam o RAG
automaticamente. Os detalhes, limites e diferenças entre sincronizar e reindexar
estão no [guia de operação](docs/OPERACAO.md).

## Verificação rápida

```powershell
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest -q
```

Os testes usam PostgreSQL descartável com `pgvector` e bloqueiam chamadas externas
de IA. Antes de executar `pytest`, inicie o contêiner descrito no
[procedimento completo](docs/MANUTENCAO.md). Não aponte os testes para o banco de uso.

## Docker

A imagem de produção está no `Dockerfile`. Consulte o [guia Docker e Render](docs/DOCKER.md) para executar e configurar as credenciais na hospedagem.

Demonstração: [treinamentos-carmel.onrender.com](https://treinamentos-carmel.onrender.com).
