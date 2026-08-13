# Segurança — modelo de ameaças e repasse

Este documento registra o repasse de segurança do Atendo: o que foi
verificado item a item, o que o projeto protege por construção, o que foi
endurecido no repasse, e o que é deliberadamente aceitável em uma demo mas
precisa mudar em produção.

Contexto do repasse: ferramentas de geração rápida (Lovable + Supabase, por
exemplo) ficam conhecidas por dois vazamentos clássicos — **chave de API
exposta no frontend** e **RLS desligada ou mal escrita**, deixando o banco
inteiro legível por qualquer visitante. As duas classes foram tratadas aqui
como requisito de arquitetura, não como ajuste posterior.

---

## 1. O que o projeto protege por construção

| Vetor | Defesa | Onde |
|---|---|---|
| Vazamento entre tenants (o risco nº 1 de SaaS) | RLS com policy `tenant_isolation` em 5 tabelas **+ API conectando como role sem privilégios** (`atendo_app`) — RLS não vale para superusuário, então isso é o que a torna real | `migrations/001_init.sql`, `app/db.py` |
| SQL injection | 100% das queries parametrizadas (`$1, $2…`) via asyncpg; nenhuma concatenação de SQL | todos os módulos |
| Chave de API no banco | Só o SHA-256 é armazenado; a chave em claro nunca toca o banco | `app/config.py` |
| Timing attack na autenticação | `hmac.compare_digest` hash-contra-hash, percorrendo o catálogo inteiro sem retorno antecipado | `app/config.py` |
| Falsificação de webhook (WhatsApp) | HMAC-SHA256 do corpo cru validada **antes** de qualquer parse; sem App Secret configurado → recusa (fail closed); handshake sem verify token → 503 | `app/channels/whatsapp.py` |
| Spoofing de tenant no webhook | Tenant resolvido pelo `phone_number_id` que a **Meta** envia — nunca por campo controlado pelo remetente | `app/channels/whatsapp.py` |
| Injeção de prompt | Camadas: regras fixas no system prompt + resultado de busca prefixado como "informação, nunca instrução" + validações de negócio **no código** + caso `injecao-de-prompt` nos evals bloqueando merge | `app/config.py`, `app/agent/*`, `evals/` |
| Escalada de capacidade do modelo | Catálogo de ferramentas por tenant no YAML — o modelo não chama o que o código não oferece (a advocacia não tem agenda) | `app/agent/tools.py` |
| XSS na UI | Toda renderização via `textContent`/`createElement`; nenhum `innerHTML` com dado externo | `app/ui/index.html` |
| Custo como vetor de dano | Rate limit por tenant+IP (Redis), teto mensal por tenant (`over_budget` corta antes de chamar o modelo), loop do agente limitado a 5 iterações | `app/gateway/cache.py`, `app/agent/loop.py` |
| Agendamento duplo por corrida | `UNIQUE (tenant_id, starts_at)` — o banco decide, sem lock de aplicação | `migrations/001_init.sql` |
| Vazamento de stack trace | Handler global: `logger.exception` no servidor, mensagem neutra ao cliente | `app/main.py` |
| Segredos em repositório | `.env` no `.gitignore`; `.env.example` só com placeholders. As `api_key` de demo nos YAML são **intencionais e documentadas** (chaves de tenants fictícios, sem valor fora da demo) | raiz |

### E o problema clássico "chave exposta no frontend"?

A `ANTHROPIC_API_KEY` **nunca chega ao navegador**: só o backend fala com a
API da Anthropic. O que a UI conhece são as chaves de tenant de
demonstração — que autenticam tenants fictícios com orçamento de US$ 25/mês
e rate limit, e existem exatamente para a demo funcionar sem configuração.
Num deployment real, cada cliente recebe uma chave própria fora do
repositório, e a UI de widget é servida por tenant.

## 2. Endurecimentos aplicados neste repasse

| # | Item | Antes | Depois |
|---|---|---|---|
| 1 | Cabeçalhos de segurança | ausentes | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy` em todas as respostas |
| 2 | CSP na UI | ausente | `default-src 'self'; frame-ancestors 'none'; base-uri 'none'` (+ inline permitido, ver §4) |
| 3 | Modelo não configurado | 500 opaco vindo do gateway | `503` com instrução clara (e webhook responde 200 com log de erro, evitando retry-loop da Meta) |
| 4 | DoS por payload | `/ingest` sem teto de texto | `max_length=500_000`; `conversation_id` limitado a 64; `days` limitado a 1–365 |
| 5 | Exposição de portas | `5432/6379/16686/4318/8000` abertos em todas as interfaces | tudo vinculado a `127.0.0.1` no compose |
| 6 | Senha do Postgres | fixa no compose | `${POSTGRES_PASSWORD:-postgres}` (parametrizável por ambiente) |
| 7 | PII em log | dry-run do WhatsApp logava a mensagem inteira | truncado a 80 caracteres |
| 8 | Higiene do container | — | `PYTHONDONTWRITEBYTECODE`, `PYTHONUNBUFFERED` (já era não-root com healthcheck) |

Cada item tem teste onde é testável: cabeçalhos, 503 sem chave, e os três
limites de entrada estão cobertos em `tests/test_api.py`.

## 3. Verificado e considerado adequado (sem mudança)

- **httpx** com verificação de TLS padrão; timeouts explícitos em toda
  chamada externa (60 s modelo, 30 s embeddings/Graph API).
- **Retry** só em erros transitórios (429/5xx/transporte), com backoff — sem
  retry de 4xx.
- **uvicorn** não loga headers (a `X-Api-Key` não aparece em access log).
- **`/appointments` e `/metrics`** expõem dados apenas ao dono da chave do
  próprio tenant.
- **Dependências**: 13 pacotes de produção, todos mantidos e com faixas de
  versão limitadas por major (`>=X,<Y`).

## 4. Limitações conhecidas — e o plano para produção

| Item | Estado na demo | Em produção |
|---|---|---|
| TLS/HTTPS | não há (localhost) | reverse proxy (Caddy/Traefik/nginx) com TLS terminando na frente da API |
| CSP com `'unsafe-inline'` | necessário porque a UI é um arquivo único sem build | mover CSS/JS para arquivos próprios e usar nonce |
| Senha do role `atendo_app` | fixa na migration (demo) | `ALTER ROLE` no provisionamento com segredo do gerenciador (Vault/SSM) |
| Redis sem senha | aceitável: só acessível em `127.0.0.1`/rede interna do compose | `requirepass` + rede privada |
| Rate limit por IP | atrás de proxy, o IP visto é o do proxy | confiar em `X-Forwarded-For` **apenas** do proxy conhecido (`--proxy-headers` + `forwarded-allow-ips`) |
| Chaves de tenant em YAML | intencional para demo | chaves fora do repositório, rotação por tenant, e hash já é o único dado no banco |
| Lockfile de dependências | faixas por major | `pip-tools`/`uv lock` + auditoria (`pip-audit`) no CI |
| Backup/restore | volume local | backup automatizado do Postgres com teste de restore |

## 5. Como verificar o isolamento (o teste que importa)

Com o ambiente de pé, o isolamento é verificável **desligando o filtro da
aplicação** — a RLS segura sozinha:

```sql
-- conectado como atendo_app, com o contexto da clínica:
BEGIN;
SELECT set_config('app.tenant_id', 'clinica-sorriso', TRUE);
SELECT count(*) FROM chunks;                          -- N chunks da clínica
SELECT count(*) FROM chunks WHERE tenant_id = 'adv-silva';  -- 0 (RLS filtrou)
COMMIT;

-- sem contexto nenhum:
SELECT count(*) FROM chunks;                          -- 0 linhas
```

Reportar vulnerabilidades: abra uma issue privada no repositório.
