# Operação e solução de problemas

[Início](../README.md) · [Configuração](CONFIGURACAO.md) · [Manutenção](MANUTENCAO.md) · [Registro](REGISTRO.md)

Use este guia depois que a aplicação estiver configurada e aberta no navegador.

## 1. Entrar e administrar usuários

1. Abra `http://127.0.0.1:8765/admin/` no ambiente local.
2. Entre com um usuário autorizado a administrar o sistema.
3. Use **Usuários → Adicionar** para criar o acesso dos colaboradores.
4. Para um colaborador comum, deixe **Membro da equipe** e **Superusuário** desmarcados.
5. Para um gestor, marque **Membro da equipe** e atribua as permissões ou grupos
   necessários. Essa marcação sozinha não concede todas as ações.

O painel mostra indicadores de setores, treinamentos, aulas e documentos conforme
as permissões do usuário, além de busca, filtros e atalhos de gerenciamento.

### Permissões

| Perfil/ação | Acesso necessário |
|---|---|
| Consultar treinamentos ativos e conversar | Usuário autenticado |
| Abrir o Admin | Usuário ativo, membro da equipe, com permissões aplicáveis |
| Ver gerenciamento de documentos | Equipe + `app.view_documento` |
| Enviar documento pela tela | Equipe + `app.view_documento` + `app.add_documento` |
| Sincronizar Drive | Equipe + `view_documento`, `add_documento`, `change_documento` e `change_treinamento` do app |
| Reindexar documento | Equipe + `app.change_documento` |
| Excluir documento | Equipe + `app.delete_documento` |

Para usar os botões na tela de documentos, o gestor também precisa conseguir
abrir essa tela. Superusuários têm acesso a todas essas ações.

Todos os colaboradores autenticados podem acessar todos os treinamentos ativos.
Ainda não existe matrícula individual nem restrição de acesso por setor.

### Primeiro acesso e senha esquecida

O administrador criado para o banco Aiven possui senha aleatória guardada no
arquivo local `.secrets/primeiro-acesso-aiven.txt`. Esse arquivo não acompanha
uma cópia do repositório e não deve ser compartilhado publicamente.

Para redefinir a senha pelo terminal, confira primeiro o banco selecionado no `.env`:

```powershell
uv run python manage.py changepassword admin
```

O comando pede a nova senha sem colocá-la na linha de comando. Substitua `admin`
se estiver alterando outro usuário. Depois da troca, a senha antiga do arquivo
de primeiro acesso deixa de funcionar. Para outra instalação, use `createsuperuser`.

## 2. Cadastrar treinamento e aulas

1. Cadastre um **Setor**, se ainda não existir.
2. Cadastre o **Treinamento**, selecione o setor e mantenha **Ativo** marcado
   enquanto ele puder ser acessado pelos colaboradores.
3. Adicione as **Aulas**, com título e ordem. Duas aulas do mesmo treinamento não
   podem usar a mesma ordem.
4. Preencha o link do vídeo e/ou a explicação em texto, conforme o conteúdo disponível.
5. Marque a aula como **Publicada**. Uma aula despublicada não aparece ao colaborador.
6. Abra o treinamento para conferir a ordem das aulas, o vídeo e os materiais.

Desativar o treinamento interrompe o acesso dos colaboradores, mas não apaga seus
documentos. Setores com treinamentos e treinamentos com documentos têm proteção
contra exclusão direta. Remova os documentos pela tela própria antes de excluir
um treinamento que não será mais usado.

## 3. Atualizar os documentos do Drive

1. Coloque os arquivos diretamente na pasta vinculada ao treinamento.
2. Abra **Treinamentos → Gerenciar documentos**.
3. Confira o link no campo **Pasta do Google Drive**.
4. Clique em **Sincronizar e indexar** e aguarde a conclusão.
5. Confira quantos documentos foram indexados ou estavam sem alterações.
6. Faça uma pergunta cuja resposta você conheça para verificar o material.

O Drive não é monitorado continuamente. Adicionar ou editar um arquivo na pasta
não atualiza o chat até você executar a sincronização.

### O que cada ação faz

| Ação | Resultado |
|---|---|
| Sincronizar e indexar | Lista a pasta e importa arquivos novos, alterados ou pendentes |
| Repetir a sincronização sem alterações | Mantém os documentos indexados, sem gerar seus embeddings novamente |
| Reindexar um documento do Drive | Baixa o conteúdo desse arquivo novamente e reconstrói seus trechos |
| Reindexar um upload manual | Lê o arquivo guardado no PostgreSQL |
| Baixar um documento do Drive | Consulta o arquivo original no Drive naquele momento |
| Excluir pela administração | Remove o cadastro, os trechos e o arquivo da aplicação, quando ela guarda uma cópia |
| Remover do Drive ou trocar o link da pasta | Não exclui documentos já importados na aplicação |

Para atualizar também nome, versão e descobrir outros arquivos, prefira
**Sincronizar e indexar**. A versão identificada pela API do Drive permite evitar
reprocessamentos. Um mesmo arquivo não duplica cadastro ao ser sincronizado de
novo no mesmo treinamento. Um upload manual e um arquivo do Drive continuam sendo
origens distintas, mesmo que tenham o mesmo nome.

A aplicação não apaga o original no Drive. Se um documento deixar de valer,
exclua-o também na administração: o chat usa os textos já indexados no banco.
Retirar o acesso ao Drive não remove automaticamente esse conteúdo do RAG.

### Quando algo falha durante a importação

Os documentos concluídos antes da falha permanecem cadastrados. O documento que
falhou na indexação fica pendente e não participa das respostas. Se uma atualização
de conteúdo falhar, o documento afetado também fica fora do chat até a correção.

Corrija a causa e execute **Sincronizar e indexar** novamente. No PostgreSQL, a
cópia temporária é removida mesmo quando há erro; a próxima tentativa baixa o
arquivo outra vez. A substituição de trechos no banco é transacional.

Se o download falhar antes de cadastrar um arquivo novo, ele pode não aparecer na
lista. Isso não significa que ele foi importado: verifique a mensagem e tente novamente.

### Formatos e limites

| Item | Limite/comportamento atual |
|---|---|
| Formatos da pasta | PDF, DOCX e Google Docs |
| Google Docs | Exportado para DOCX antes da extração |
| Arquivos por pasta/treinamento | Até 100 documentos compatíveis diretamente na pasta |
| Tamanho por documento | `MAX_UPLOAD_MB`, padrão 10 MB |
| Subpastas e atalhos | Não percorridos/importados |
| Planilhas e apresentações | Não importadas |
| PDF | Até 300 páginas, sem senha |
| PDF digitalizado como imagem | Precisa de OCR prévio; a aplicação não faz OCR |
| Texto extraído | Até 2 milhões de caracteres por documento |
| Trechos | Até 1000 por documento |
| DOCX | Até 50 MB descomprimidos e 2000 entradas internas; macros rejeitadas |

O limite também é verificado durante o download, não só pelo tamanho declarado.
Os arquivos passam por validação de nome, extensão, tipo e estrutura/assinatura.
[Download e exportação pela API do Drive](https://developers.google.com/workspace/drive/api/guides/manage-downloads).

## 4. Enviar um arquivo sem usar o Drive

1. Abra **Gerenciar documentos** no treinamento correto.
2. Selecione um PDF ou DOCX em **Enviar PDF ou DOCX**.
3. Clique em **Enviar e indexar**.
4. Aguarde **Indexado** antes de testar o chat.

O arquivo original do upload manual fica no próprio banco, junto
com o cadastro e os trechos. Isso consome armazenamento do Aiven.
A extração e a geração de embeddings são as mesmas.

## 5. Vídeos do Google Drive

No cadastro da aula, use um link HTTPS de **arquivo de vídeo**, por exemplo:

```text
https://drive.google.com/file/d/ID_DO_VIDEO/view
https://drive.google.com/open?id=ID_DO_VIDEO
```

O link pode incluir `resourcekey`. Links de pasta não são aceitos como vídeo.

O player próprio mantém os controles abaixo da imagem para evitar cobrir a pessoa
ou o conteúdo, especialmente no celular. Há reprodução/pausa, progresso, tempo,
ícone de áudio e tela cheia. Sem JavaScript, o navegador usa controles nativos;
no iOS, a tela cheia também pode usar o player do sistema.

**O vídeo e os documentos usam acessos diferentes:** a conta de serviço foi integrada
à leitura de documentos. O player atual de vídeo retransmite um arquivo acessível
sem sessão Google no servidor; ele não usa o JSON do Drive para vídeos privados.
Quando isso não for possível, **Abrir vídeo** encaminha ao Drive, que pode pedir login.

No navegador do computador simulando celular, o mouse pode manter controles
nativos visíveis. O player próprio foi criado para evitar essa sobreposição no
fluxo normal. O vídeo é transmitido pelo servidor em blocos; seu tráfego passa
pela hospedagem, sem salvar o vídeo inteiro em disco.

## 6. Usar e entender o chat

O assistente responde em português, com linguagem amigável, usando os materiais
indexados do treinamento. Não lê vídeos nem a explicação digitada na aula.

A busca recupera até 15 trechos e descarta os que ultrapassam a distância
configurada. O modelo precisa indicar referências válidas internamente; a interface
remove números de citação e rodapés de fontes para exibir apenas a conversa.
Essa verificação não garante, sozinha, que toda resposta esteja correta: valide
o conteúdo com os procedimentos oficiais antes de liberar o treinamento.

Se não houver informação suficiente, o bot informa que não encontrou a resposta.
Se não houver materiais disponíveis e indexados, a aplicação pede que a indexação
seja verificada, em vez de enviar a pergunta ao modelo.

O histórico é mantido em `sessionStorage`, na sessão da aba do navegador, separado
por usuário e treinamento, limitado às últimas 20 mensagens. Não é salvo como
histórico no PostgreSQL nem enviado junto nas próximas perguntas. Evite perguntas
como “e nesse caso?” sem contexto; escreva uma pergunta completa. **Limpar conversa**
apaga o histórico exibido.

No celular e tablet até 1000 px, use as abas **Conteúdo** e **Assistente**. Enter
insere uma linha; envie pelo botão. No computador, Enter envia. Durante a resposta,
três pontos animados indicam o processamento.

## 7. Diagnóstico dos erros mais comuns

| Sintoma/mensagem | O que verificar e fazer |
|---|---|
| Configure as credenciais do Google Drive | Confira a variável `GOOGLE_APPLICATION_CREDENTIALS`, o caminho completo do JSON, o tipo conta de serviço e o reinício do servidor |
| Link compartilhado, mas continua sem acesso | Compartilhe com o e-mail da conta de serviço; “qualquer pessoa com o link” não configura a credencial do programa |
| Não foi possível acessar a pasta ou arquivo | Confira Drive API habilitada, ID correto, arquivo fora da lixeira e acesso da conta; erros 401/403/404 da API recebem mensagem segura |
| Funcionava localmente, falhou no Render | O caminho `C:/...` não existe no servidor; configure Secret File e `/etc/secrets/google-drive.json` |
| Arquivo não apareceu na sincronização | Confira formato aceito, pasta correta e se não está em subpasta/atalho; leia também o erro da operação |
| Documento pendente | Corrija credencial, cota ou conteúdo e repita a sincronização/reindexação; ele não entra nas respostas |
| Documento sem texto extraível | Abra o PDF e tente selecionar o texto; se for imagem, faça OCR antes |
| Arquivo excede o tamanho permitido | Reduza/divida o documento; o limite por arquivo vale também para o Drive |
| Não achei essa informação | Confira se a informação está no material indexado do mesmo treinamento; formule a pergunta explicitamente e teste o trecho esperado |
| Modelo ou dimensão incompatível | Reindexe os materiais com a configuração atual de embeddings |
| Limite de requisições atingido / HTTP 429 | Aguarde a janela/cota do provedor; confira o painel da API; não clique repetidamente em indexar |
| Credencial inválida / modelo indisponível | Confira a chave e o modelo do provedor indicado; reinicie após alterar o `.env` |
| `DATABASE_URL` inválida | Use URI completa, sem quebra de linha nem `CLICK_TO:REVEAL_PASSWORD`, com usuário, senha e banco correto |
| Falha de conexão com PostgreSQL | Confira disponibilidade no Aiven, host, porta, senha, TLS, regras de rede e limite de conexões |
| Erro de certificado TLS | Confira CA correta, arquivo disponível no servidor e hostname da URI; não desative TLS remoto |
| Relação/tabela ou tipo `vector` inexistente | Confira o banco selecionado e execute `uv run python manage.py migrate` com usuário autorizado |
| Administração negada / HTTP 403 | Confira usuário ativo, membro da equipe e permissões da ação; para CSRF, confira sessão e configuração HTTPS/host |
| Login antigo não funciona após trocar de banco | Usuários pertencem ao banco escolhido. Use o administrador criado no Aiven ou redefina sua senha |
| Vídeo não toca na página | Confira link de arquivo, aula publicada, treinamento ativo e leitura do vídeo sem sessão Google; tente Abrir vídeo |
| A mudança no `.env` não entrou | Pare/reinicie o processo e confira se o terminal/hospedagem já define a variável com outro valor |

Para diagnóstico, compartilhe a mensagem, a ação executada e o horário. Não
compartilhe senha, URI completa do banco, chaves das APIs ou conteúdo do JSON.
