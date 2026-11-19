"""Agente de ampliação do banco de perguntas da Minerva (FCT/UFPA).

Rodar dentro do container da interface:
    docker exec -it ufpa_rag_ui python scripts/agente_ampliacao.py gerar --rodadas 40
    docker exec -it ufpa_rag_ui python scripts/agente_ampliacao.py auditar
    docker exec -it ufpa_rag_ui python scripts/agente_ampliacao.py aplicar --csv tests/data/agente/candidatos_AAAAMMDD.csv

O agente NUNCA altera o catálogo sozinho. Ciclo de cada rodada (modo gerar):
  1. escolhe um trecho de documento oficial (documentos_ufpa) cujas páginas
     ainda não são cobertas por nenhuma entrada do catálogo;
  2. pede ao modelo local (Qwen) perguntas que um discente da FCT faria e que
     o trecho responde, com resposta curta e a citação literal que a sustenta;
  3. verifica a coerência sem confiar no modelo:
       a. a citação existe literalmente no trecho;
       b. todo número/data/artigo da resposta aparece no trecho;
       c. um segundo passe do modelo (juiz) confirma que a resposta decorre
          da citação e está no escopo FCT/UFPA;
       d. a busca híbrida da Minerva recupera esse mesmo trecho para a
          pergunta (senão a entrada nunca seria achada em produção);
       e. a pergunta não duplica uma entrada existente (se for parecida,
          vira candidata a VARIAÇÃO daquela entrada);
       f. o PDF local confere (SHA-256) com o publicado no site oficial
          *.ufpa.br listado em fontes_documentais.json;
  4. grava candidatos em tests/data/agente/candidatos_<data>.jsonl e .csv para
     revisão humana (coluna "decisao": APROVAR / REJEITAR).

Modo auditar: confere as respostas literais já existentes contra as páginas
citadas (números ausentes, escopo copiado de outra entrada, juiz).
Modo aplicar: inclui no minerva_dataset.json apenas as linhas APROVAR do CSV,
com status "contextualizada_sem_aprovacao_institucional".
"""
import argparse
import csv
import hashlib
import json
import random
import re
import sys
import time
import unicodedata
from contextlib import closing
from datetime import date
from pathlib import Path
from urllib.request import Request

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

DATASET = RAIZ / "minerva_dataset.json"
FONTES = RAIZ / "fontes_documentais.json"
SAIDA = RAIZ / "tests" / "data" / "agente"

# ----------------------------------------------------------------- utilidades


def norm(texto):
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^\w\s]", " ", t.lower())
    return re.sub(r"\s+", " ", t).strip()


_VAZIAS = set("a o os as de da do das dos e em no na nos nas um uma para pra por com que qual quais "
              "como se eu meu minha ufpa fct posso pode sao e ser tem ha".split())


def tokens(texto):
    return {p for p in norm(texto).split() if p not in _VAZIAS and len(p) > 1}


def jaccard(a, b):
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


_NUM = re.compile(r"\d+(?:[.,/]\d+)*")


def numeros(texto):
    return {n.replace(".", "").replace(",", "") for n in _NUM.findall(str(texto or ""))}


def citacao_no_trecho(citacao, trecho):
    # Compara sem espaços: o texto extraído do PDF parte palavras ("dem onstre").
    c = norm(citacao).replace(" ", "")
    return len(c) >= 20 and c in norm(trecho).replace(" ", "")


def numeros_sustentados(resposta, trecho):
    faltam = numeros(resposta) - numeros(trecho)
    return sorted(faltam)


def extrair_json(texto):
    texto = re.sub(r"^```(?:json)?|```$", "", (texto or "").strip(), flags=re.M).strip()
    ini = min([i for i in (texto.find("["), texto.find("{")) if i >= 0], default=-1)
    if ini < 0:
        return None
    for fim in range(len(texto), ini, -1):
        try:
            return json.loads(texto[ini:fim])
        except ValueError:
            continue
    return None


def barra(n, total, t0, rotulo=""):
    total = max(total, 1)
    w = 30
    f = int(w * n / total)
    dec = time.monotonic() - t0
    eta = dec / n * (total - n) if n else 0
    hms = lambda s: time.strftime("%H:%M:%S", time.gmtime(s))
    sys.stdout.write(f"\r[{'#' * f}{'.' * (w - f)}] {n}/{total} {100 * n // total:3d}%  "
                     f"{hms(dec)} ETA {hms(eta)}  {rotulo[:40]:<40}")
    sys.stdout.flush()


# ------------------------------------------------------------------- catálogo


def carregar_catalogo(caminho=DATASET):
    dados = json.loads(Path(caminho).read_text())
    return dados, dados["respostas_especificas"]


def cobertura(entradas):
    cob = {}
    for e in entradas:
        ctx = e.get("contexto_documental") or {}
        doc = ctx.get("documento") or e.get("fonte_documento")
        for p in ctx.get("paginas_fisicas") or []:
            cob.setdefault(doc, set()).add(int(p))
    return cob


def frases(entrada):
    return [entrada.get("pergunta", "")] + list(entrada.get("variacoes") or [])


def mais_parecida(pergunta, entradas):
    melhor, nota = None, 0.0
    for e in entradas:
        if not e.get("ativo", True):
            continue
        for f in frases(e):
            j = jaccard(pergunta, f)
            if j > nota:
                melhor, nota = e, j
    return melhor, nota


# ------------------------------------------------------------------------ LLM

PROMPT_GERAR = """Você ajuda a montar o banco de perguntas da Minerva, assistente dos discentes da \
Faculdade de Engenharia da Computação e Telecomunicações (FCT/ITEC/UFPA).
Abaixo está um trecho OFICIAL do documento "{doc}" (páginas {pi}-{pf}).

Escreva até 3 perguntas que um aluno da FCT/UFPA realmente faria e que ESTE trecho responde \
sozinho. Para cada uma dê:
- "pergunta": como o aluno escreveria (pode ser informal);
- "variacoes": 2 outras formas de perguntar a mesma coisa;
- "resposta": 1 a 3 frases, citando o artigo/inciso quando houver, sem inventar nada fora do trecho;
- "citacao": cópia LITERAL (palavra por palavra) da frase do trecho que sustenta a resposta;
- "dispositivo": artigo/parágrafo/item (ou "" se não houver).
Se o trecho não tiver conteúdo útil para alunos (sumário, assinatura, cabeçalho), responda [].
Responda SOMENTE com uma lista JSON.

TRECHO:
\"\"\"{trecho}\"\"\""""

PROMPT_JUIZ = """Você é um verificador rigoroso. Diga se a RESPOSTA é totalmente sustentada pela \
CITAÇÃO do documento oficial e responde à PERGUNTA, no contexto da graduação FCT/UFPA.
PERGUNTA: {pergunta}
RESPOSTA: {resposta}
CITAÇÃO: \"\"\"{citacao}\"\"\"
Responda SOMENTE com JSON: {{"sustentada": true|false, "responde": true|false, "motivo": "..."}}"""


def _aguardar_modelo(limite=180):
    import requests
    from config import LLM_API_URL
    base = LLM_API_URL.split("/v1/")[0]
    fim = time.monotonic() + limite
    while time.monotonic() < fim:
        try:
            if requests.get(base + "/health", timeout=5).ok:
                return True
        except Exception:
            pass
        time.sleep(5)
    return False


def llm(prompt, max_tokens=900, tentativas=3):
    import requests
    for t in range(tentativas):
        try:
            return _llm(prompt, max_tokens)
        except (requests.ConnectionError, requests.Timeout):
            if t == tentativas - 1 or not _aguardar_modelo():
                raise
            print("\n  modelo reiniciou; retomando…")


def _llm(prompt, max_tokens):
    import requests
    from config import LLM_API_URL
    r = requests.post(LLM_API_URL, timeout=(5, 400), json={
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2, "max_tokens": max_tokens, "cache_prompt": True,
        "chat_template_kwargs": {"enable_thinking": False}})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def juiz(pergunta, resposta, citacao, chamar=llm):
    v = extrair_json(chamar(PROMPT_JUIZ.format(pergunta=pergunta, resposta=resposta, citacao=citacao), 200))
    if not isinstance(v, dict):
        return False, "juiz sem JSON"
    return bool(v.get("sustentada")) and bool(v.get("responde")), str(v.get("motivo", ""))[:200]


# -------------------------------------------------------------- site oficial

_SHA_SITE = {}


def conferir_site(doc, sha_local):
    """Baixa o PDF do site oficial (*.ufpa.br) e compara o SHA-256."""
    if doc in _SHA_SITE:
        sha = _SHA_SITE[doc]
    else:
        url = json.loads(FONTES.read_text()).get(doc) if FONTES.exists() else None
        if not url:
            _SHA_SITE[doc] = "sem_url"
            return "sem_url_oficial"
        try:
            from web_segura import abrir_url
            with abrir_url(Request(url, headers={"User-Agent": "Minerva-agente"}), timeout=20) as r:
                sha = hashlib.sha256(r.read()).hexdigest()
        except Exception as exc:  # rede bloqueada, 404 etc.
            sha = "erro:" + type(exc).__name__
        _SHA_SITE[doc] = sha
    if sha == "sem_url":
        return "sem_url_oficial"
    if sha.startswith("erro:"):
        return "site_inacessivel(" + sha[5:] + ")"
    return "confere_com_site" if sha == sha_local else "DIFERE_DO_SITE"


# ------------------------------------------------------------------- verificar


def verificar(cand, trecho, entradas, recuperou, chamar=llm):
    """Aplica as checagens a um candidato. Devolve (status, motivos, parecida)."""
    motivos = []
    if not citacao_no_trecho(cand.get("citacao", ""), trecho["conteudo"]):
        motivos.append("citação não está literalmente no trecho")
    faltam = numeros_sustentados(cand.get("resposta", ""), trecho["conteudo"])
    if faltam:
        motivos.append("números fora do trecho: " + ",".join(faltam))
    parecida, nota = mais_parecida(cand.get("pergunta", ""), entradas)
    if not motivos:
        ok, motivo = juiz(cand["pergunta"], cand["resposta"], cand["citacao"], chamar)
        if not ok:
            motivos.append("juiz: " + motivo)
    if not recuperou:
        motivos.append("busca híbrida não recupera este trecho (precisa de entrada no catálogo)")
    if motivos and not (len(motivos) == 1 and motivos[0].startswith("busca")):
        return "REPROVADO", motivos, parecida, nota
    if nota >= 0.6:
        return "VARIACAO", motivos, parecida, nota
    return "NOVA", motivos, parecida, nota


# ----------------------------------------------------------------------- modos


def trechos_sem_cobertura(conn, cob, limite):
    with conn.cursor() as cur:
        cur.execute("""SELECT id, nome_arquivo, conteudo, pagina_inicio, pagina_fim, documento_sha256
                       FROM documentos_ufpa WHERE length(conteudo) > 400 AND pagina_inicio IS NOT NULL""")
        linhas = [dict(zip(("id", "doc", "conteudo", "pi", "pf", "sha"), r)) for r in cur.fetchall()]
    livres = [t for t in linhas
              if not (set(range(t["pi"], (t["pf"] or t["pi"]) + 1)) & cob.get(t["doc"], set()))]
    random.shuffle(livres)
    # Regimento Geral e documentos de gestão ficam por último: o banco é para o discente.
    livres.sort(key=lambda t: t["doc"] in _DOCS_DE_GESTAO)
    return livres[:limite], len(livres), len(linhas)


_DOCS_DE_GESTAO = {"RegimentoGeral.pdf", "Regimento_FCT.pdf"}


def modo_gerar(args):
    from scripts.ingestao import conectar_banco
    from minerva_hybrid import buscar_em_documentos_postgres
    _, entradas = carregar_catalogo()
    SAIDA.mkdir(parents=True, exist_ok=True)
    tag = date.today().strftime("%Y%m%d")
    jl = SAIDA / f"candidatos_{tag}.jsonl"
    vistos = set()
    if jl.exists():
        vistos = {json.loads(l)["trecho_id"] for l in jl.read_text().splitlines() if l.strip()}
    with closing(conectar_banco()) as conn:
        alvo, livres, total = trechos_sem_cobertura(conn, cobertura(entradas), args.rodadas + len(vistos))
        alvo = [t for t in alvo if t["id"] not in vistos][:args.rodadas]
        print(f"Trechos no índice: {total} | sem cobertura no catálogo: {livres} | nesta execução: {len(alvo)}")
        cont = {"NOVA": 0, "VARIACAO": 0, "REPROVADO": 0}
        t0 = time.monotonic()
        with jl.open("a") as saida:
            for i, t in enumerate(alvo, 1):
                barra(i - 1, len(alvo), t0, f"{t['doc']} p.{t['pi']}")
                try:
                    cands = extrair_json(llm(PROMPT_GERAR.format(
                        doc=t["doc"], pi=t["pi"], pf=t["pf"], trecho=t["conteudo"][:3500]))) or []
                except Exception as exc:
                    print(f"\n  erro no modelo: {type(exc).__name__}")
                    continue
                site = conferir_site(t["doc"], t["sha"])
                for c in cands if isinstance(cands, list) else []:
                    if not isinstance(c, dict) or not c.get("pergunta") or not c.get("resposta"):
                        continue
                    fontes = buscar_em_documentos_postgres(conn, c["pergunta"]) or []
                    recuperou = any(f.get("id") == t["id"] or (
                        f.get("titulo", f.get("nome_arquivo")) == t["doc"] and f.get("pagina_inicio") == t["pi"])
                        for f in fontes if isinstance(f, dict))
                    status, motivos, parecida, nota = verificar(c, t, entradas, recuperou)
                    cont[status] += 1
                    saida.write(json.dumps({
                        "status": status, "pergunta": c["pergunta"], "variacoes": c.get("variacoes", [])[:3],
                        "resposta": c["resposta"], "citacao": c.get("citacao", ""),
                        "dispositivo": c.get("dispositivo", ""), "documento": t["doc"],
                        "paginas": list(range(t["pi"], (t["pf"] or t["pi"]) + 1)), "documento_sha256": t["sha"],
                        "trecho_id": t["id"], "recuperado_pela_busca": recuperou, "site_oficial": site,
                        "parecida_com": parecida.get("id") if parecida else None, "similaridade": round(nota, 2),
                        "motivos": motivos}, ensure_ascii=False) + "\n")
                    saida.flush()
                barra(i, len(alvo), t0, f"novas {cont['NOVA']} var {cont['VARIACAO']} rep {cont['REPROVADO']}")
    print()
    exportar_csv(jl)
    print(f"Resultado: {cont} -> {jl.with_suffix('.csv')}")


def exportar_csv(jl):
    linhas = [json.loads(l) for l in jl.read_text().splitlines() if l.strip()]
    with jl.with_suffix(".csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["decisao", "status", "pergunta", "variacoes", "resposta", "citacao", "dispositivo",
                    "documento", "paginas", "site_oficial", "recuperado_pela_busca", "parecida_com",
                    "similaridade", "motivos", "trecho_id"])
        for c in linhas:
            w.writerow(["", c["status"], c["pergunta"], " | ".join(c["variacoes"]), c["resposta"],
                        c["citacao"], c["dispositivo"], c["documento"], ",".join(map(str, c["paginas"])),
                        c["site_oficial"], c["recuperado_pela_busca"], c["parecida_com"] or "",
                        c["similaridade"], " ; ".join(c["motivos"]), c["trecho_id"]])


def escopos_suspeitos(entradas):
    """Escopo com termos raros que combinam com OUTRA entrada e não com a própria
    (sinal de texto copiado de uma entrada vizinha). Devolve {id: motivo}."""
    from collections import Counter
    esc = {e["id"]: (e.get("contexto_documental") or {}).get("escopo", "") for e in entradas}
    n = max(sum(1 for v in esc.values() if v), 1)
    df = Counter(t for v in esc.values() if v for t in tokens(v))
    texto = {e["id"]: tokens(" ".join(frases(e)) + " " + (e.get("resposta_literal") or e.get("resposta_esperada") or ""))
             for e in entradas}
    achados = {}
    for e in entradas:
        raros = {t for t in tokens(esc[e["id"]]) if df[t] < 0.05 * n}
        if len(raros) < 3 or not e.get("ativo", True):
            continue
        proprio = len(raros & texto[e["id"]])
        for outro, v in esc.items():
            if outro != e["id"] and v == esc[e["id"]] and len(raros & texto[outro]) >= proprio + 3:
                achados[e["id"]] = f"escopo igual ao de {outro} e fala de: {', '.join(sorted(raros - texto[e['id']])[:6])}"
                break
        else:
            if proprio == 0:
                achados[e["id"]] = "escopo com termos que não aparecem na pergunta/resposta: " + ", ".join(sorted(raros)[:6])
    return achados


def modo_auditar(args):
    from scripts.ingestao import conectar_banco
    _, entradas = carregar_catalogo()
    SAIDA.mkdir(parents=True, exist_ok=True)
    alvo = [e for e in entradas if e.get("ativo", True) and e.get("resposta_literal")
            and (e.get("contexto_documental") or {}).get("paginas_fisicas")]
    suspeitos = escopos_suspeitos(entradas)
    achados = []
    t0 = time.monotonic()
    with closing(conectar_banco()) as conn, conn.cursor() as cur:
        for i, e in enumerate(alvo, 1):
            barra(i - 1, len(alvo), t0, e["id"])
            ctx = e["contexto_documental"]
            cur.execute("""SELECT string_agg(conteudo, ' ') FROM documentos_ufpa WHERE nome_arquivo=%s
                           AND pagina_inicio <= %s AND pagina_fim >= %s""",
                        (ctx["documento"], max(ctx["paginas_fisicas"]), min(ctx["paginas_fisicas"])))
            texto = cur.fetchone()[0] or ""
            prob = []
            if not texto:
                prob.append("páginas citadas não existem no índice")
            else:
                ident = json.dumps(ctx, ensure_ascii=False) + " " + str(e.get("fonte_documento", ""))
                faltam = [x for x in numeros_sustentados(e["resposta_literal"], texto)
                          if x not in numeros(ident) and not re.fullmatch(r"\d{1,4}/\d{4}", x)]
                if faltam:
                    prob.append("números fora das páginas: " + ",".join(faltam))
            if e["id"] in suspeitos:
                prob.append(suspeitos[e["id"]])
            if args.juiz and texto:
                ok, motivo = juiz(e["pergunta"], e["resposta_literal"], texto[:3500])
                if not ok:
                    prob.append("juiz: " + motivo)
            if prob:
                achados.append({"id": e["id"], "pergunta": e["pergunta"], "documento": ctx["documento"],
                                "paginas": ctx["paginas_fisicas"], "problemas": prob})
            barra(i, len(alvo), t0, f"achados {len(achados)}")
    print()
    destino = SAIDA / f"auditoria_{date.today():%Y%m%d}.json"
    destino.write_text(json.dumps(achados, ensure_ascii=False, indent=1))
    print(f"{len(achados)} entradas com indício de incoerência -> {destino}")


def completar_contextos(entradas, pasta=Path("/documentos")):
    """Preenche SHA-256, escopo, dispositivo e evidências (texto integral da
    página, como em validar_pdfs) de qualquer entrada com contexto_documental
    ainda sem evidências (criadas pelo agente ou por curadoria manual)."""
    from pypdf import PdfReader
    cache, feitos = {}, 0
    for e in entradas:
        c = e.get("contexto_documental") or {}
        if not c or c.get("evidencias"):
            continue
        doc = c["documento"]
        if doc not in cache:
            caminho = pasta / doc
            cache[doc] = (hashlib.sha256(caminho.read_bytes()).hexdigest(),
                          [" ".join((pg.extract_text() or "").split()) for pg in PdfReader(caminho).pages])
        sha, paginas = cache[doc]
        c["documento_sha256"] = sha
        c["dispositivo"] = c.get("dispositivo") or f"trecho das páginas {', '.join(map(str, c['paginas_fisicas']))}"
        c.setdefault("escopo", f"Graduação da UFPA/FCT, conforme {doc} ({c['dispositivo']}); "
                               "não estender a outros níveis de ensino sem previsão expressa.")
        c["evidencias"] = [{"pagina_fisica": n, "texto": paginas[n - 1],
                            "texto_sha256": hashlib.sha256(paginas[n - 1].encode()).hexdigest()}
                           for n in c["paginas_fisicas"]]
        e["fonte_documento"] = doc
        feitos += 1
    return feitos


def modo_completar(args):
    dados, entradas = carregar_catalogo()
    n = completar_contextos(entradas)
    DATASET.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n")
    print(f"{n} entradas completadas com SHA-256 e evidências.")


def modo_aplicar(args):
    dados, entradas = carregar_catalogo()
    por_id = {e["id"]: e for e in entradas}
    with open(args.csv, encoding="utf-8-sig") as f:
        aprovadas = [r for r in csv.DictReader(f, delimiter=";") if r["decisao"].strip().upper() == "APROVAR"]
    maior, menor, _ = (int(x) for x in dados["versao_dataset"].split("."))
    versao = f"{maior}.{menor + 1}.0"
    prox = max(int(e["id"].split("_")[1]) for e in entradas) + 1
    novas = var = 0
    for r in aprovadas:
        frases_novas = [r["pergunta"]] + [v.strip() for v in r["variacoes"].split("|") if v.strip()]
        if r["status"] == "VARIACAO" and r["parecida_com"] in por_id:
            alvo = por_id[r["parecida_com"]]
            existentes = {norm(x) for x in frases(alvo)}
            for fr in frases_novas:
                if norm(fr) not in existentes:
                    alvo.setdefault("variacoes", []).append(fr)
                    existentes.add(norm(fr))
            var += 1
            continue
        paginas = [int(p) for p in r["paginas"].split(",") if p]
        entradas.append({
            "id": f"MINERVA_{prox:04d}", "macroarea": "Ampliação pelo agente", "intent": "agente_ampliacao",
            "pergunta": frases_novas[0], "variacoes": frases_novas[1:], "entidades": [], "palavras_chave": [],
            "fonte_esperada": r["documento"], "url_oficial": json.loads(FONTES.read_text()).get(r["documento"], ""),
            "estrategia_recuperacao": "RESPOSTA_LITERAL", "resposta_literal": r["resposta"],
            "fonte_documento": r["documento"], "temporal": False, "prioridade": "Baixa",
            "tipo_resposta": "informativa", "resposta_esperada": r["resposta"], "ativo": True,
            "versao_dataset": versao,
            "origem_entrada": {"tipo": "agente_ampliacao", "lote": date.today().strftime("%Y%m%d"),
                               "data": date.today().isoformat(), "base": f"trecho {r['trecho_id']} revisado"},
            "status_curadoria": "contextualizada_sem_aprovacao_institucional", "autorizacao_literal": "pendente",
            "contexto_documental": {"status": "localizado_na_copia_local", "documento": r["documento"],
                                    "paginas_fisicas": paginas, "dispositivo": r["dispositivo"],
                                    "citacao": r["citacao"], "site_oficial": r["site_oficial"],
                                    "revisao": "conferencia_tecnica_documental; nao_e_aprovacao_institucional"}})
        prox += 1
        novas += 1
    completar_contextos(entradas)
    dados["versao_dataset"] = versao
    copia = DATASET.with_suffix(f".antes_{versao}.json")
    copia.write_text(DATASET.read_text())
    DATASET.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n")
    print(f"Versão {versao}: {novas} entradas novas, {var} com variações acrescentadas (backup: {copia.name}).")
    print("Agora: python scripts/atualizar_evidencias_ampliacao.py && python scripts/sincronizar_qa.py")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="modo", required=True)
    g = s.add_parser("gerar")
    g.add_argument("--rodadas", type=int, default=30, help="trechos analisados nesta execução")
    g.add_argument("--semente", type=int, default=None)
    a = s.add_parser("auditar")
    a.add_argument("--juiz", action="store_true", help="também pede parecer do modelo (mais lento)")
    ap = s.add_parser("aplicar")
    ap.add_argument("--csv", required=True)
    s.add_parser("completar")
    args = p.parse_args()
    if getattr(args, "semente", None) is not None:
        random.seed(args.semente)
    {"gerar": modo_gerar, "auditar": modo_auditar, "aplicar": modo_aplicar,
     "completar": modo_completar}[args.modo](args)


if __name__ == "__main__":
    main()
