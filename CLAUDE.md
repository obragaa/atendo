# Atendo — briefing de retomada

> **Este arquivo é lido automaticamente pelo Claude Code ao abrir esta pasta.**
> Leia-o antes de agir. O relato completo da construção está em
> [docs/HISTORICO-SESSAO.md](docs/HISTORICO-SESSAO.md).

## O que é

Agente de atendimento **multi-tenant** para pequenas empresas: responde por
WhatsApp e por um widget web com base nos documentos de cada cliente, agenda
horários e registra leads. Projeto de **portfólio**, tratado com seriedade de
produto de mercado.

Os três diferenciais (é o que o projeto vende):
1. **Custo medido por conversa** (`usage_events` → `cost_per_conversation_usd`).
2. **Qualidade verificável** — evals comportamentais bloqueiam merge no CI.
3. **Isolamento entre clientes garantido pelo banco** (RLS + role sem privilégios).

A fonte de verdade da implementação é [SPEC.md](SPEC.md); as escolhas de
arquitetura estão em [DECISIONS.md](DECISIONS.md); o repasse de segurança em
[SECURITY.md](SECURITY.md).

## Estado atual (13/08/2026) — ENTREGUE E NO AR

- **7 fases do SPEC implementadas e validadas.** 74 testes (~1,5 s, sem banco,
  Redis ou chave de API), `ruff check` limpo, CI verde.
- **Security review aplicado**: cabeçalhos + CSP, limites de entrada, 503
  explicativo sem chave, portas de infra em `127.0.0.1`, PII truncada em log.
- **Rodando localmente via Docker**: 4 serviços healthy, seed aplicado, smoke
  tests verdes (401/401/503, métricas, UI+CSP, ingestão idempotente) e **RLS
  provada no psql** (contexto da clínica vê 5 chunks, `adv-silva` 0, sem
  contexto 0).
- **GitHub**: https://github.com/obragaa/atendo (público, `main`, até `bca6844`).
- **Documentação em 3 níveis + campanha de marketing** — ver `docs/`.

## Comandos nesta máquina (Windows) — armadilhas já resolvidas

```powershell
# testes e lint (NÃO existe `make` no Windows)
.\.venv\Scripts\python.exe -m pytest -q -p no:warnings
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format .

# docker (o docker.exe NÃO está no PATH da sessão)
$docker = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
& $docker compose up -d --build
& $docker compose exec -T api python -m scripts.seed
# UI http://localhost:8000 · API /docs · Jaeger http://localhost:16686
```

- **`.ps1` deve ser salvo em UTF-8 COM BOM.** O PowerShell 5.1 lê `.ps1` sem
  BOM como ANSI e quebra em acentos e travessões (já custou uma rodada).
- **O caminho tem acento** (`Portfólio`). Evite passá-lo entre processos; dentro
  de scripts use `Resolve-Path "$env:USERPROFILE\Desktop\Portf*lio\atendo"`.
- `Invoke-WebRequest` precisa de `-UseBasicParsing` (sessão não-interativa).
- Contar testes: `pytest --collect-only -q` não devolve nada útil aqui; use a
  API do pytest com um plugin de `pytest_collection_finish`.

## Publicar no GitHub

Não há `gh` CLI e o Git Credential Manager não tem credencial salva. O fluxo que
funciona (e está roteirizado em `scripts/push-github.ps1`):

1. Device flow com o client_id público do GitHub CLI `178c6fc778ccc68e1d6a`,
   **escopo `repo workflow`** — só `repo` é recusado por causa de
   `.github/workflows/ci.yml`.
2. O usuário digita o código em https://github.com/login/device.
3. O push lê o token **de um arquivo**; nunca passe token na linha de comando
   (o classificador de auto-mode bloqueia) e apague o arquivo depois.

Identidade git da máquina: `Felipe Braga Duarte` · conta GitHub: **obragaa**.

## Pendências

- **Pode haver commit local não publicado.** Confira com
  `git log --oneline origin/main..main`; se listar algo, rode
  `.\scripts\push-github.ps1` e peça ao usuário para digitar o código.
  (O commit `05a5726`, com estes arquivos de contexto, ficou assim: o código de
  autorização expirou antes de o usuário digitá-lo.)
- **`ANTHROPIC_API_KEY` não está configurada.** Sem ela o `/chat` responde 503
  com instrução (comportamento projetado). Para o chat conversar de verdade:
  colar a chave em `.env` e `docker compose up -d`.
- **Gravar o vídeo da demo** (roteiro pronto na seção 10 do
  `docs/guia-didatico.pdf`) — melhora muito o Post 1 do LinkedIn.
- **Publicar a campanha do LinkedIn** (`docs/linkedin/`, calendário de 6 semanas).
- Deploy público (Render/Railway/Fly.io) nunca foi feito — hoje roda só local.

## Como o usuário quer trabalhar (respeitar)

- **Português do Brasil** em tudo: código, comentários, docs e conversa.
- **Modo automático**: quando houver um plano ou SPEC, executar fase a fase sem
  parar para pedir permissão — validando (testes + lint) ao fim de cada uma.
- **Personas de engenharia por área** (arquiteto, DBA, AppSec, frontend, SRE,
  redator comercial) — as skills em `~/.claude/skills` são a referência.
- **Seriedade de mercado**, mesmo sendo portfólio.
- **Nunca inflar tempo de trabalho.** O posicionamento comercial é o oposto:
  *"fiz em DIAS o que o mercado cobra em meses e dezenas de milhares"* — o
  mérito está em saber orquestrar IA com método de engenharia. Nunca escrever
  "passei semanas".
- Não sujar a Área de Trabalho: temporário vai no scratchpad da sessão.

## Mapa de `docs/`

| Arquivo | Público |
|---|---|
| `apresentacao-comercial.pdf` | **Venda** — dono de empresa, zero tecniquês |
| `guia-didatico.pdf` | Leigo curioso — analogias, ilustrações, roteiro de demo |
| `dossie-tecnico.pdf` | Engenheiro/recrutador técnico |
| `linkedin/post-1..9-*.txt` | 9 posts prontos para colar |
| `linkedin/*.pdf` e `img-recibo.png` | Carrosséis e imagem da campanha |
| `linkedin/posts-extras.md` | Calendário de 6 semanas + regras de funil |
| `HISTORICO-SESSAO.md` | O relato completo da construção |
