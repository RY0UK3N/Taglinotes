# Taglinotes

Aplicativo Windows para organizar serviços, clientes e cobranças. Interface nativa Python/Tk e banco SQLite local; sem dependências Python externas.

## Iniciar

Requer Python 3.12 ou superior com Tk. Execute `Iniciar.ps1` pelo PowerShell. O script procura primeiro o Python do Codex e, depois, `pythonw.exe` no PATH. Ele inicia a API local e abre o aplicativo. Use `-ApiOnly` para iniciar apenas a integração, inclusive por um atalho na pasta Inicializar do Windows.

## Funcionalidades

- Clientes com aliases normalizados, ignorando acentos, maiúsculas e espaços.
- Serviços com valor em centavos, mensagem original preservada e edição antes do fechamento.
- Regras semanais ou mensais; preços e prazos desconhecidos ficam pendentes de conferência.
- Agrupamento de serviços do mesmo cliente, rascunho para nota e pagamento integral.
- Cores e texto para cobranças vencidas ou próximas; histórico de alterações.
- Mensagens pendentes, backup consistente e atualização manual da lista de serviços.

A mudança de periodicidade só afeta serviços novos. Os prazos existentes podem ser editados individualmente antes do agrupamento. Aliases adicionais não removem os anteriores.

## Integração n8n

A API escuta somente em `127.0.0.1:8765`. No Docker Desktop, o n8n usa `http://host.docker.internal:8765`.

`GET /health` informa a disponibilidade. Os POST exigem `Authorization: Bearer <token>`. O token é gerado em `dados/integration-token.txt`; registre-o em uma credencial Header Auth no n8n. Nunca publique esse arquivo.

1. `POST /v1/messages`: `chat_id`, `message_id`, `text`, `sent_at` (ISO 8601).
2. Interpretar e validar o relato no n8n.
3. `POST /v1/services`: `chat_id`, `message_id`, `client`, `date` (AAAA-MM-DD), `description`, `amount_cents` (inteiro ou null).
4. Confirmada a gravação local, continuar o registro secundário na planilha.

A origem é única. Repetir uma entrega não duplica o serviço nem substitui a mensagem original ou uma edição manual. Clientes desconhecidos são cadastrados sem regra de cobrança. No n8n, configure retentativas nos HTTP Requests e salvamento do progresso das execuções.

## Dados e backup

Banco, token e backups ficam em `dados/`, ignorado pelo Git. Faça backups pelo aplicativo para outro disco ou local protegido. O backup automático de inicialização é apenas uma cópia local, substituída a cada abertura. Para restaurar, feche o aplicativo e a API, preserve o banco atual e substitua `dados/taglinotes.sqlite` por um backup consistente. Preserve o token separadamente.

## Limites atuais

Um serviço por mensagem; texto original, sem cópia de anexos. Não há emissão fiscal, pagamentos parciais, fusão de clientes existentes ou notificações com o aplicativo fechado. As mensagens pendentes exigem conferência e retentativa no n8n; não há processador automático dessa fila.

A recuperação de mensagens recebidas com o notebook desligado ainda não está garantida: versões do Telegram Trigger podem registrar o webhook com `drop_pending_updates`. Isso exige validação específica, além do limite de retenção do Telegram. Não considere as retentativas HTTP uma solução para esse problema.

## Testes

`python -m unittest discover -s . -v`

Testes cobrem normalização, datas de vencimento, prevenção de duplicatas, imutabilidade da mensagem original, fechamento transacional e backup. A integração também deve ser testada no n8n com os nós de planilha e IA simulados, evitando cobranças e escritas de teste em produção.
