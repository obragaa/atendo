# Kit de divulgação — LinkedIn

Três posts prontos (é só copiar, ajustar e publicar), mais a estratégia de
sequência, mídia e horários. Escritos em primeira pessoa, no seu lugar.

---

## A estratégia em 30 segundos

1. **Poste em sequência, não tudo de uma vez.** Post 1 (lançamento) → espere
   4–7 dias → Post 2 (bastidores técnicos) → 4–7 dias → Post 3 (visão de
   negócio). Cada um alcança um público diferente e reaquece o anterior.
2. **Vídeo vence.** Grave a demo de ~2–3 min seguindo o roteiro do
   `guia-didatico.pdf` (seção 10) e anexe no Post 1. Vídeo nativo no LinkedIn
   alcança muito mais que link.
3. **Link do GitHub no primeiro comentário**, não no corpo do post — o
   LinkedIn reduz o alcance de posts com link externo.
4. **Melhor horário:** terça a quinta, entre 8h e 10h da manhã.
5. **Responda todo comentário nas primeiras 2 horas** — é o que mais puxa
   alcance no algoritmo.
6. **Hashtags:** 4 a 6 por post, misturando amplas e específicas (sugestões
   em cada post abaixo).

---

## POST 1 — Lançamento (ancoragem: dias vs meses, quase zero vs R$ 50 mil+)

**→ Versão final pronta para colar em `linkedin/post-1-lancamento.txt`**, com
o carrossel em `linkedin/carrossel-post1.pdf` (8 slides) e o roteiro de
publicação passo a passo.

O ângulo: *"o mercado cobra meses e dezenas de milhares por um sistema assim;
eu fiz em dias, quase de graça — porque sei usar IA com método de engenharia.
E o que eu fiz para o atendimento, faço para qualquer dor da sua empresa."*
Gatilhos: ancoragem de preço/prazo, prova concreta (recibo, testes, código
aberto), autoridade técnica e CTA duplo (recrutadores + empresas na DM).

**Mídia:** o carrossel PDF (ou o vídeo da demo, se gravado — roteiro na
seção 10 do guia didático; nesse caso troque "Nos slides abaixo" por "No
vídeo abaixo").
**Primeiro comentário:** já incluído no arquivo .txt.

---

## POST 2 — Bastidores técnicos (para devs e recrutadores)

> "Melhorei o prompt" é opinião. Teste automatizado é fato.
>
> Construí o Atendo (agente de atendimento multi-tenant) em poucos dias,
> usando IA como copiloto de engenharia — e o que prova que ele não é código
> descartável são justamente as decisões. As que mais me orgulham ficaram de
> FORA:
>
> ❌ Sem LangChain — o loop do agente tem ~60 linhas de Python legível.
> Framework esconderia exatamente a parte que precisa ser depurável.
>
> ❌ Sem banco vetorial dedicado — pgvector no Postgres que já estava lá.
> Uma dependência a menos, backup único, transação com o resto.
>
> ❌ Sem classificador de roteamento de modelo — o barato (Claude Haiku)
> atende tudo; o caro (Sonnet) só entra quando o barato falha DE VERDADE.
> Regra que não adivinha não erra.
>
> E as que ficaram dentro:
>
> ✅ Row Level Security no Postgres com role sem privilégios — um WHERE
> esquecido devolve zero linhas, nunca dados de outro cliente.
>
> ✅ Suíte de avaliação comportamental no CI: 8 casos com gabarito, incluindo
> injeção de prompt. Abaixo de 85% de acerto, o merge é bloqueado.
>
> ✅ 74 testes que rodam em 1,5 segundo sem banco, sem Redis e sem chave de
> API — dublê para tudo que é externo.
>
> ✅ Cada centavo de cada chamada de modelo gravado em usage_events —
> cost_per_conversation_usd é a métrica que precifica a mensalidade.
>
> Stack: Python 3.12, FastAPI, PostgreSQL 16 + pgvector, Redis, API da
> Anthropic via httpx puro, OpenTelemetry, Docker Compose, GitHub Actions.
>
> O DECISIONS.md documenta cada escolha com a alternativa descartada e o que
> me faria mudar de ideia. Link no primeiro comentário. 👇
>
> #Python #FastAPI #PostgreSQL #LLM #EngenhariaDeSoftware #IA

**Mídia:** carrossel de prints — o recibo na UI, o diagrama de arquitetura do
dossiê, o trecho do DECISIONS.md, o CI verde no Actions.
**Primeiro comentário:** link do repo + "os PDFs em docs/ têm a versão
técnica e a versão para quem não é de TI".

---

## POST 3 — Visão de negócio (para donos de empresa e potenciais clientes)

> São 23h de domingo. Alguém manda mensagem para a clínica:
> "Quanto custa a limpeza? Vocês atendem meu convênio?"
>
> Na maioria das empresas, essa mensagem espera até segunda de manhã.
> Só que o cliente não espera: ele manda a mesma pergunta para o
> concorrente — e marca com quem responder primeiro.
>
> Construí o Atendo para esse momento exato.
>
> É um atendente virtual que estudou a SUA empresa — preços, serviços,
> regras, horários — e responde por ela em segundos, a qualquer hora. Marca
> horário na agenda. Anota quem se interessou para a equipe retornar.
>
> E com três garantias que robô comum não dá:
>
> 1️⃣ O que ele não sabe, ele não inventa — encaminha para a equipe.
> 2️⃣ Ninguém convence ele a dar desconto que você não autorizou.
> 3️⃣ Você vê o custo de cada conversa, em centavos, num painel.
>
> Cabe em clínica, escritório, salão, academia, oficina, imobiliária —
> colocar uma empresa nova no ar leva um dia.
>
> E aqui está a parte que quase ninguém conta: um sistema desses não precisa
> mais de meses de projeto nem de orçamento de dezenas de milhares. Sabendo
> usar IA com método, ele nasce em dias — e sob medida para a SUA operação.
>
> Quer ver funcionando com as informações do seu negócio? A demonstração
> leva 15 minutos. Me chama. 📩
>
> #Atendimento #PequenasEmpresas #WhatsApp #IA #Automacao #Empreendedorismo

**Mídia:** a página 1 do `apresentacao-comercial.pdf` como imagem (a conversa
de domingo 23h é o gancho visual) ou o vídeo da demo reaproveitado.
**Primeiro comentário:** "Para quem é de TI e quer ver por dentro:
https://github.com/obragaa/atendo".

---

## Checklist de mídia (antes de postar)

- [ ] Gravar o vídeo da demo (roteiro: guia-didatico.pdf, seção 10, ~3 min)
      — OBS Studio ou a gravação de tela do Windows (Win+G) resolvem.
- [ ] Tirar 4 prints: recibo na UI · seletor de tenants · resposta recusando
      o desconto · Jaeger com o trace da conversa.
- [ ] Exportar a página 1 do PDF comercial como imagem (abrir no navegador →
      print) para o Post 3.
- [ ] Conferir se o repositório está com o README aparecendo bonito no
      GitHub (primeira impressão de recrutador).
- [ ] Atualizar o título do perfil no LinkedIn antes do Post 1 (ex.:
      "Desenvolvedor · IA aplicada a atendimento · Python/FastAPI").

## Ideias de continuação (se os posts renderem)

- Thread/artigo: "5 decisões que tomei construindo um agente de IA — e as
  alternativas que descartei" (é o DECISIONS.md em formato de artigo).
- Post curto: só o print do recibo com a legenda "quanto custou esta
  conversa? $0.00342. Eu sei porque medi." — gancho forte para debate.
- Vídeo curto: 60s tentando "hackear" o próprio bot com injeção de prompt e
  ele resistindo — formato que performa bem.
