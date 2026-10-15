# Preparar a API VideoHub na Vercel

A Vercel consegue executar este FastAPI como função Python. O deploy deve ser
feito como um projeto separado do frontend, com `backend` como diretório raiz.
O endpoint da aplicação é definido em `app/main.py`.

## Persistência

Funções Vercel não mantêm o arquivo local `videos.db` nem os arquivos em
`storage/`. O backend usa a base SQLite local durante o desenvolvimento; no
deploy, a configuração `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN` liga o mesmo
ORM a uma base Turso/libSQL remota, compatível com SQLite.

O dialeto SQLAlchemy de libSQL está marcado pelo mantenedor como experimental.
Esta preparação mantém o ORM existente, mas recomenda-se validar o comportamento
e os limites do serviço antes de usar a aplicação em produção.

Vídeos e miniaturas existentes precisam estar em Vercel Blob. O script de
migração envia os arquivos diretamente do computador para o Blob e copia os
registros para uma base Turso vazia. Ele não envia os vídeos através de uma
função Vercel, cujo limite de corpo de requisição é 4,5 MB.

## Variáveis do projeto Vercel

Configure-as no painel da Vercel, nunca neste repositório:

- `TURSO_DATABASE_URL`: URL `libsql://...` da base remota.
- `TURSO_AUTH_TOKEN`: token privado da base.
- `VIDEOHUB_ALLOW_PUBLIC_UPLOADS`: mantenha `false`; o endpoint de upload da
  API retorna 501 na Vercel porque o limite de requisição não permite receber
  os vídeos. Os endpoints de leitura e registro de visualização continuam ativos.
- `FRONTEND_ORIGINS`: origem exata do frontend publicado, por exemplo
  `https://pogramador-frontend--vth9njtkic.expo.app`.

Conecte também uma Blob Store ao projeto Vercel para usar o token OIDC gerenciado
pela Vercel. Para a migração executada localmente, use `BLOB_READ_WRITE_TOKEN`
em uma sessão local privada, ou as credenciais OIDC da Vercel. Nunca coloque
tokens no código, no frontend ou em arquivos versionados.

## Migração local, quando custos forem aprovados

1. Crie a base Turso e a Blob Store somente depois de revisar os preços e
   limites atuais desses serviços.
2. Configure localmente `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` e a credencial
   de gravação do Blob. Não publique esses valores.
3. Como o driver libSQL não fornece wheel Windows, execute a migração em Linux
   ou WSL 2, com o repositório e a pasta `backend/storage` acessíveis. A partir
   do diretório `backend`, rode:

   ```bash
   python -m pip install -r requirements-migration.txt
   python -m scripts.migrate_to_turso_and_blob --confirm-public-upload
   ```

   O script exige a confirmação explícita, recusa uma base Turso que já tenha
   vídeos e não apaga nem modifica o SQLite local.
4. Só depois da migração, crie o projeto de backend na Vercel apontando para
   `backend` e configure as variáveis listadas acima.
5. Configure o frontend publicado para usar a URL HTTPS da API Vercel e
   publique novamente o frontend.

Nenhum serviço é criado, nenhum vídeo é transferido e nenhuma publicação é
feita por este preparo.
