# Registro das configurações e melhorias

[Início](../README.md) · [Configuração](CONFIGURACAO.md) · [Operação](OPERACAO.md) · [Manutenção](MANUTENCAO.md)

Registro da implementação e conferência em **16/10/2026**, horário de Brasília.
As seções iniciais descrevem a implantação original; a seção de limpeza ao final
registra as remoções posteriores e o estado atual simplificado.
Os números abaixo são uma fotografia desse momento e podem mudar com o uso.
Senhas, URIs com credenciais e conteúdo do JSON foram excluídos desta documentação.

## 1. Ambiente configurado e conferido

| Item | Situação verificada |
|---|---|
| Aplicação | Django executado localmente, com dados persistidos no Aiven |
| Banco | PostgreSQL, banco dedicado `treinamentos` |
| Estrutura | Migrações `0001` a `0004` aplicadas; a última realiza a limpeza descrita abaixo |
| Busca vetorial | Extensão `vector` ativa; textos e embeddings no PostgreSQL |
| Treinamento | Integração, setor RH, vinculado à pasta do Drive informada pelo responsável |
| Quantidades na conferência | 1 treinamento, 1 aula, 1 documento indexado e 55 trechos |
| Documentos | Importação de 1 PDF do Drive concluída |
| Embeddings | `models/gemini-embedding-001`, 768 dimensões |
| Respostas | `nvidia/nemotron-3.5-super-vl:free`, pelo OpenRouter, no ambiente conferido |
| Credenciais | Chaves configuradas e JSON do Drive acessível localmente |
| Administrador inicial | Criado com senha aleatória; primeiro acesso registrado apenas em `.secrets/primeiro-acesso-aiven.txt` |
| Dados anteriores | SQLite e banco anterior do serviço Aiven preservados, sem importação de dados antigos |
| Hospedagem | Não publicada no Render nem no Cloud Run nesta etapa |

A aula registrada nesta conferência já foi cadastrada após a preparação inicial
do banco. O comando `setup_training` não cria aulas automaticamente.

## 2. Ajustes da aplicação

| Área | O que foi feito | Por quê |
|---|---|---|
| Organização | Views separadas por treinamento, chat, documentos e vídeo; serviços para processamento | Facilitar leitura, manutenção e testes |
| Administração | Painel com indicadores, busca, filtros e atalhos; permissões por ação | Centralizar a gestão dos treinamentos |
| RAG | Recuperação ampliada para até 15 trechos, com filtro de distância e escopo de treinamento | Encontrar páginas relevantes que ficavam depois de capas e sumários |
| Documentos pendentes | Bloqueio do uso no chat até concluir a indexação | Evitar respostas baseadas em uma atualização incompleta |
| Conversa | Prompt em português, tom natural e direto, sem rodapés de fonte na interface | Melhorar a experiência dos colaboradores |
| Citações | Validação interna mantida; marcadores e rodapés removidos da apresentação | Manter rastreabilidade técnica sem poluir a conversa |
| Carregamento | Três pontos animados no chat | Comunicar processamento sem mensagens técnicas desnecessárias |
| Celular | Abas de conteúdo/assistente, ajustes de teclado, rolagem e alvos de toque | Priorizar o uso em telefones |
| Vídeo | Player próprio, proporção preservada e controles abaixo da imagem | Evitar corte e controles sobrepostos ao conteúdo |
| Áudio | Ícones de alto-falante ativo/silenciado | Tornar o controle mais claro |
| Identidade | Cores e fontes do material oficial; logotipo completo Carmel Hotéis | Alinhar o produto à marca |
| Tema | Modos claro/escuro, preferência no navegador e integração com o Admin | Melhorar legibilidade em diferentes ambientes |
| Logotipo | PNG transparente; marrom no claro e branco por filtro CSS nas superfícies escuras; remoção do fundo e do nome Academia | Preservar o desenho oficial e simplificar o cabeçalho |

Os arquivos de marca e sua origem estão descritos em
[Identidade visual](../app/static/brand/README.md). O logotipo completo não foi
redesenhado por IA. A versão branca exibida no cabeçalho usa o mesmo PNG com
filtro CSS, não um segundo arquivo do logotipo completo.

## 3. Integração do Drive

Foi implementado um cliente autenticado da API do Drive, com escopo somente de
leitura, listagem paginada, limite de arquivos, download limitado e exportação de
Google Docs para DOCX. A pasta é cadastrada por treinamento na administração.

A configuração local passou a apontar para o JSON da conta de serviço por
`GOOGLE_APPLICATION_CREDENTIALS`. O acesso real à pasta foi verificado; o PDF foi
baixado, extraído e indexado. A sincronização reconhece o ID e a versão do arquivo
e permite retomar documentos pendentes sem duplicar o cadastro do mesmo arquivo.

As mensagens de erro orientam sobre credencial, acesso, formato, tamanho e cotas.
Não foi implementada sincronização automática nem exclusão automática ao remover
um arquivo da pasta.

## 4. Banco novo no Aiven

1. A conexão completa foi localizada no arquivo de exemplo durante a configuração.
2. Ela foi transferida para o `.env`, retirando a credencial do modelo versionável.
3. Foi verificado que o banco inicialmente indicado já tinha tabelas; criou-se
   `treinamentos` separado para não modificar esses dados.
4. As migrações criaram o esquema e ativaram `pgvector`.
5. Foram criados o administrador inicial e o treinamento vinculado ao Drive.
6. O PDF foi indexado novamente a partir do Drive, gerando 55 trechos no novo banco.

Foi adicionada seleção de backend por `DATABASE_URL`, validação da URI, TLS remoto
e configuração opcional de CA. A busca no PostgreSQL é exata por cosseno, com
substituição transacional e validação de modelo/dimensão.

Os documentos do Drive passaram a usar arquivos temporários no modo PostgreSQL.
Uploads manuais ficam como binários no banco. Downloads e reindexações do Drive
consultam a origem novamente. O índice e o chat não exigem a cópia local do PDF.

## 5. Validações executadas na implementação

- 202 testes gerais passaram no ambiente SQLite isolado.
- 12 testes específicos passaram com PostgreSQL/pgvector real em contêiner temporário.
- Total: 214 testes aprovados; os 12 de PostgreSQL são pulados na execução padrão
  sem `TEST_DATABASE_URL` e são executados no procedimento separado.
- O contêiner e seus dados descartáveis foram removidos depois dos testes.
- `manage.py check`, verificação de migrações e conferência do lock de dependências passaram.
- A conexão real com Aiven, as migrações, a importação do PDF e uma resposta real
  do RAG foram verificadas.
- Login do novo administrador, catálogo, painel, treinamento e gerenciamento de
  documentos responderam HTTP 200 na verificação autenticada.
- O uso em telas móveis e a troca de tema foram verificados em navegador durante
  os ajustes de interface. Isso não substitui testes em todos os modelos de celular.

## 6. O que permanece para uma próxima etapa

A publicação no Render/Cloud Run, o servidor de produção, a entrega dos estáticos
e os testes no domínio HTTPS real continuam pendentes. A documentação distingue
essas orientações futuras das configurações já executadas.

Também não foram implementados OCR, transcrição de vídeos, filas de processamento,
restrição por matrícula/setor nem sincronização agendada. O plano gratuito das
APIs não é uma garantia de capacidade para todos os funcionários.

## 7. Revisão desta documentação

O README foi reorganizado como ponto de entrada, com guias separados para
configuração, operação, manutenção e este registro. A descrição anterior que
apresentava apenas Chroma foi atualizada para o backend PostgreSQL em uso.

Foram conferidos os nomes das variáveis contra o código e o `.env.example`, os
links locais, a estrutura Markdown, a codificação UTF-8, a ausência dos valores
reais das credenciais nos guias e a sintaxe de 14 blocos PowerShell. O estado do
ambiente foi consultado sem alterar os dados e sem executar novas chamadas de IA.

Nesta revisão passaram novamente 202 testes gerais; os 12 específicos de
PostgreSQL não foram reexecutados, pois a mudança foi somente documental. A
verificação do Django e a conferência de migrações também passaram. O procedimento
de backup/restauração e a publicação em hospedagem foram documentados, mas não
executados nesta revisão.

## 8. Limpeza após a adoção de PostgreSQL e Drive

Foi retirado o suporte operacional a SQLite/Chroma. A aplicação agora exige
`DATABASE_URL` e utiliza somente PostgreSQL com `pgvector`. O banco do Aiven,
as aulas, os documentos e os trechos existentes foram mantidos.

Remoções e simplificações:

- Dependência Chroma e seu conjunto de pacotes auxiliares: o lock passou de 110
  para 38 pacotes, com 70 pacotes instalados removidos do ambiente.
- Importador legado e testes específicos do fluxo anterior.
- Variáveis `DJANGO_DATABASE_PATH`, `LEGACY_DATABASE_PATH`, `DATABASE_PATH`,
  `DOCUMENTS_PATH` e `VECTOR_DB_PATH`, inclusive dos arquivos de configuração locais.
- Implementações duplicadas de índice: `vector_store.py` passou a conter apenas
  PostgreSQL, e `postgres_vectors.py` foi removido.
- Campo de caminho local dos documentos e verificações de existência em disco.
- Escrita persistente de PDFs no projeto e ramificações para armazenamentos antigos.
- Remoção manual dos vetores na exclusão: a relação com o documento utiliza a
  exclusão em cascata do banco.
- Compatibilidade com IDs de modelo usados pelo adaptador antigo de agentes.

Uma migração adicional verifica se todos os documentos têm origem no Drive ou
arquivo no banco antes de retirar o campo legado. Essa proteção foi testada com
um documento que dependia de disco: a migração recusou a alteração até o original
ser preservado no banco. No Aiven não havia documentos dependentes de disco.

Os diretórios antigos `app/database`, `media` e `vector_db`, além do backup local
anterior à integração, foram movidos para `.archive/legacy-local-20261016`.
Esse arquivo histórico não é usado pela aplicação e é ignorado pelo Git. A chave
de sessão local em `.cache/django-secret`, o `.env` e os arquivos em `.secrets`
continuam preservados. Arquivos temporários de revisão e teste foram removidos.

Os testes passaram a usar somente PostgreSQL descartável, sem consultar o Aiven
do `.env` automaticamente. A suíte final passou com **197 testes**, incluindo o
teste de proteção da migração. A diferença para os 214 testes anteriores decorre
da retirada dos cenários exclusivos dos componentes removidos e da inclusão da
nova proteção. Não há testes pulados por falta de backend SQLite/PostgreSQL.

## 9. Simplificação da abertura do chat e ícone da aba

Foram removidas as três perguntas sugeridas e o rodapé de orientação abaixo do
campo de mensagem, junto com o JavaScript e CSS exclusivos desses elementos.
O campo mantém seu rótulo acessível e os atalhos de teclado existentes.

As páginas da aplicação e do Admin passaram a usar o símbolo oficial Carmel
como favicon PNG, com versão branca para a preferência escura do navegador.
Os títulos das abas do catálogo e treinamento também passaram a identificar
Carmel Hotéis. Os arquivos de marca existentes foram reutilizados.
