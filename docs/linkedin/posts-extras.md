# Posts extras — a campanha completa

Seis posts novos, cada um mirando um público com um gatilho diferente.
Junto com os 3 do kit original, você tem **9 peças = 5 a 6 semanas de
conteúdo**. O calendário sugerido está no final.

Legenda de cada post: 🎯 público · 🧠 gatilho · 🖼 mídia · 💬 1º comentário

---

## POST 4 — "Enquanto você dorme" (donos de negócio)

🎯 Donos de pequenas empresas · 🧠 aversão à perda + urgência
🖼 `carrossel-conta.pdf` (6 slides: a matemática da perda vs centavos)

> Fiz uma conta que incomoda.
>
> Uma clínica comum recebe ~15 mensagens fora do horário por semana.
> Se 2 ou 3 fechariam tratamento com resposta rápida, e o ticket médio é
> R$ 300… são R$ 2.400 a R$ 3.600 POR MÊS escorrendo em silêncio.
>
> (Números ilustrativos — troque pelos seus. A sua conta dói mais ou menos?)
>
> O detalhe cruel: essa perda não aparece em relatório nenhum. Cliente que
> não foi respondido não reclama — ele simplesmente marca com o concorrente
> e você nunca fica sabendo que ele existiu.
>
> Do outro lado da balança: um atendente com IA que responde em segundos,
> 24/7, com as informações da SUA empresa, custa CENTAVOS por conversa.
> E no sistema que eu construí, cada centavo aparece num painel — medido,
> não estimado.
>
> Não estou falando de robô que inventa resposta: ele não promete o que você
> não autorizou, não dá diagnóstico, não mistura seus dados com os de
> ninguém — e o que não sabe, passa para a sua equipe.
>
> A matemática completa está nos slides. 👇
>
> Se a conta da perda te incomodou, me chama na DM: em 15 minutos eu te
> mostro funcionando com os dados do seu negócio.
>
> #PequenasEmpresas #Atendimento #IA #Automacao #Gestao

💬 "Para quem quiser ver por dentro (ou mostrar pro seu TI):
https://github.com/obragaa/atendo — código aberto e documentado."

---

## POST 5 — "IA não substitui dev" (devs e tech — polêmica construtiva)

🎯 Desenvolvedores, tech leads, CTOs · 🧠 controvérsia + identidade de grupo
🖼 Sem mídia (texto puro performa melhor em polêmica) ou `img-recibo.png`

> "IA vai substituir programador" é o debate errado.
>
> A pergunta certa: por que dois devs com a mesma ferramenta entregam
> resultados tão diferentes?
>
> Eu construí um agente de atendimento multi-tenant em poucos dias usando
> IA pesadamente. E o que saiu do outro lado NÃO foi código descartável:
>
> — 74 testes automatizados rodando em 1,5 segundo
> — suíte de avaliação comportamental que BLOQUEIA merge se o agente ceder
>   a um golpe de engenharia social
> — isolamento entre clientes imposto pelo banco (RLS), não por um if
> — cada decisão documentada com a alternativa descartada
>
> A diferença não está na IA. Está no que você exige dela:
>
> 1. Especificação antes de código. A IA executa mil vezes melhor quando o
>    contrato está escrito.
> 2. Testes como cerca, não como enfeite. Ela refatora sem medo quando a
>    suíte segura.
> 3. Revisão de segurança como fase, não como remendo.
> 4. Decisões documentadas — porque quem revisa a arquitetura ainda sou eu.
>
> IA não substitui engenheiro. Ela AMPLIFICA o que você já é: quem entrega
> código frágil, agora entrega código frágil mais rápido. Quem tem método,
> entrega sistema de produção em dias.
>
> O projeto está aberto — julgue o código, não o discurso. Link no primeiro
> comentário.
>
> Concorda ou discorda? Me conta aí embaixo. 👇
>
> #DesenvolvimentoDeSoftware #IA #EngenhariaDeSoftware #Python #Carreira

💬 "O repositório completo, com DECISIONS.md e SECURITY.md:
https://github.com/obragaa/atendo"

---

## POST 6 — O recibo (impacto rápido, alcance amplo)

🎯 Todos (post de descoberta) · 🧠 curiosidade + especificidade de número
🖼 `img-recibo.png` (imagem única 1080×1080)

> $0.00342.
>
> É quanto custou esta conversa do meu agente de IA — e eu sei o número
> exato porque cada resposta sai com um recibo: fonte consultada, custo e
> tempo.
>
> A maioria das empresas usando IA hoje não sabe responder uma pergunta
> simples: "quanto custa cada atendimento seu?"
>
> A minha responde sozinha. Literalmente.
>
> Sistema completo, aberto, no link do primeiro comentário. E se a sua
> empresa quer IA COM medidor — não no escuro — me chama. 📊
>
> #IA #CustoPorConversa #Transparencia #Automacao

💬 "O projeto: https://github.com/obragaa/atendo — o recibo aparece embaixo
de cada resposta na interface. Centavos, medidos chamada a chamada."

---

## POST 7 — "Tentei enganar meu robô" (segurança — devs + geral)

🎯 Devs, entusiastas de IA, curiosos · 🧠 desafio + storytelling de conflito
🖼 `carrossel-golpe.pdf` (7 slides: os 4 ataques falhando)

> Passei uma tarde tentando enganar meu próprio robô de atendimento.
>
> Fingi ser o dono exigindo 90% de desconto. Pedi dados de outros clientes.
> Simulei documento com instrução escondida. Tentei fazê-lo rodar em círculos
> até estourar a fatura de IA.
>
> Falhei nas quatro. E cada fracasso foi projetado — não sorte:
>
> → Desconto não é decisão do modelo. É código, e conversa não muda código.
> → Dados de outro cliente? O banco filtra cada linha pelo dono. O robô não
>   enxerga o que não é dele — nem pedindo com licença.
> → Documento "envenenado" chega carimbado: informação, nunca instrução.
> → Custo tem três freios: limite por minuto, teto de rodadas, orçamento
>   mensal. Bug não vira fatura.
>
> E a parte que mais importa: esses golpes viraram TESTES AUTOMÁTICOS. Toda
> mudança no código passa por eles de novo. Se o robô ceder, a mudança não
> entra no ar.
>
> Segurança de IA não é prompt bonito pedindo "por favor não faça coisas
> ruins". É engenharia.
>
> Os 4 ataques, slide a slide. 👇 E o código aberto no primeiro comentário.
>
> #SegurancaDaInformacao #IA #PromptInjection #Engenharia #LLM

💬 "Repo com o SECURITY.md completo (modelo de ameaças item a item):
https://github.com/obragaa/atendo"

---

## POST 8 — A jornada (storytelling pessoal — rede em geral)

🎯 Rede ampla, recrutadores, conexões novas · 🧠 identificação + inspiração
🖼 `carrossel-post1.pdf` reaproveitado, ou sem mídia

> Uma coisa que aprendi construindo meu último projeto:
>
> a habilidade mais valiosa de 2026 não é escrever código. É saber
> EXATAMENTE o que exigir dele.
>
> Construí um sistema de atendimento com IA — do banco de dados à interface,
> da segurança à documentação — em poucos dias. Não porque digito rápido:
> porque mudei meu papel.
>
> Deixei de ser a pessoa que escreve cada linha e virei a pessoa que:
>
> → escreve a especificação que não deixa margem para "achismo"
> → define o que é inaceitável (inventar preço, vazar dado, estourar custo)
> → exige o teste que prova cada regra
> → revisa cada decisão como se fosse dinheiro meu em produção
>
> A IA escreveu muito código comigo. Mas especificação, critério e ceticismo
> — isso não se terceiriza.
>
> Resultado: um sistema que uma software house entregaria em meses, pronto
> em dias, documentado em três níveis (até minha avó entenderia o guia), e
> com uma suíte de testes que me deixa dormir tranquilo.
>
> Se você é dev: aprenda a orquestrar, não só a digitar.
> Se você tem uma empresa: o custo de automatizar despencou — quem souber
> aproveitar primeiro, larga na frente.
>
> O projeto está aberto no primeiro comentário. E minha DM também. 🚀
>
> #Carreira #IA #Desenvolvimento #Produtividade #FuturoDoTrabalho

💬 "O projeto: https://github.com/obragaa/atendo — com a documentação em
três níveis na pasta docs/."

---

## POST 9 — Enquete (engajamento barato para reaquecer)

🎯 Todos · 🧠 participação de baixo esforço (o algoritmo ama enquete)
🖼 Enquete nativa do LinkedIn (Começar publicação → ⋯ → Criar enquete)

**Pergunta:** Sua empresa responde clientes fora do horário comercial?

**Opções:**
1. Sim, alguém responde na hora
2. Só no dia seguinte 😬
3. Depende de quem viu a mensagem
4. Nem sei quantas chegam à noite

**Duração:** 1 semana

**Texto do post:**
> Pergunta honesta para quem tem (ou trabalha em) empresa que atende pelo
> WhatsApp: o que acontece com a mensagem que chega às 22h?
>
> Contexto: construí recentemente um sistema que responde em segundos,
> 24/7, com as informações da empresa — e descobri que o problema não é a
> tecnologia (ela ficou barata). É que a maioria nem mede quantas mensagens
> perde.
>
> Vota aí — o resultado me diz qual conteúdo trago a seguir. 👇

💬 Ao final da enquete, comente o resultado e emende o Post 4 (a conta da
perda) como sequência natural.

---

# Calendário da campanha (9 peças, ~6 semanas)

| Semana | Post | Público | Mídia |
|---|---|---|---|
| 1 (ter) | **1 — Lançamento** (dias vs meses) | geral | carrossel-post1.pdf |
| 1 (sex) | **6 — O recibo** ($0.00342) | geral/descoberta | img-recibo.png |
| 2 (qua) | **2 — Bastidores técnicos** | devs/recrutadores | prints do repo/CI |
| 3 (ter) | **9 — Enquete** | todos | enquete nativa |
| 3 (sex) | **4 — A conta da perda** | donos de negócio | carrossel-conta.pdf |
| 4 (qua) | **7 — Tentei enganar meu robô** | devs + geral | carrossel-golpe.pdf |
| 5 (ter) | **5 — IA não substitui dev** | devs (polêmica) | texto puro |
| 5 (sex) | **3 — Visão de negócio** | donos/clientes | apresentacao p.1 |
| 6 (qua) | **8 — A jornada** | rede ampla | reaproveita post1 |

**Regras de ouro da campanha:**
- Nunca dois posts no mesmo dia; mínimo 2 dias entre posts.
- Link SEMPRE no primeiro comentário, nunca no corpo.
- Responder todo comentário em até 2 horas (combustível de alcance).
- Quem comentar em post de negócio (4, 3, 9) é lead: puxe para a DM com
  oferta da demonstração de 15 minutos.
- Quem comentar em post técnico (2, 5, 7) é rede: pergunte de volta,
  gere conversa — recrutador lê comentário.
- Se um post render acima da média, NÃO emende outro no dia seguinte:
  deixe-o respirar mais 2 dias.
