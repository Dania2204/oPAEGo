"""Tablero de control XP de PAEGo, generado desde los issues y milestones de GitHub.

Lee los issues (historias, tareas, pruebas y defectos) y los milestones (etapas XP) de los dos
repositorios y publica el resumen:
- en el resumen de la ejecución de GitHub Actions (GITHUB_STEP_SUMMARY);
- en el issue fijado "Tablero de control" del repo web (si ACTUALIZAR_ISSUE=1).

Solo usa la biblioteca estándar. Variables: GITHUB_TOKEN, REPOS (owner/repo separados por coma),
REPO_TABLERO (donde vive el issue del tablero).
"""

import json
import os
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone

TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPOS = [r.strip() for r in os.environ.get("REPOS", "Dania2204/oPAEGo,Dania2204/paego-mobile").split(",") if r.strip()]
REPO_TABLERO = os.environ.get("REPO_TABLERO", REPOS[0])
TITULO_ISSUE = "Tablero de control (dashboard XP)"
PROYECTO = os.environ.get("PROYECTO_URL", "https://github.com/users/St-Alejo/projects/4")
HOY = date.today()


def api(ruta, metodo="GET", datos=None):
    req = urllib.request.Request(
        "https://api.github.com" + ruta,
        method=metodo,
        data=json.dumps(datos).encode() if datos is not None else None,
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "tablero-xp"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or "null")


def paginas(ruta):
    out, pag = [], 1
    while True:
        lote = api(f"{ruta}{'&' if '?' in ruta else '?'}per_page=100&page={pag}")
        out += lote
        if len(lote) < 100:
            return out
        pag += 1


def campos(cuerpo):
    """Lee la tabla | Campo | Valor | del cuerpo del issue."""
    c = {}
    for m in re.finditer(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$", cuerpo or "", re.M):
        k, v = m.group(1), m.group(2)
        if k not in ("Campo", "---") and not set(k) <= {"-"}:
            c.setdefault(k, v)
    return c


def num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------ datos
ETAPAS = {}
ISSUES = []
for repo in REPOS:
    for m in paginas(f"/repos/{repo}/milestones?state=all"):
        f = re.match(r"(\d{4}-\d{2}-\d{2}) → (\d{4}-\d{2}-\d{2})\. ?(.*)", m.get("description") or "", re.S)
        e = ETAPAS.setdefault(m["title"], {"titulo": m["title"], "inicio": f.group(1) if f else None,
                                           "fin": f.group(2) if f else (m["due_on"] or "")[:10],
                                           "objetivo": f.group(3).strip() if f else "", "abiertos": 0, "cerrados": 0})
        e["abiertos"] += m["open_issues"]
        e["cerrados"] += m["closed_issues"]
    for i in paginas(f"/repos/{repo}/issues?state=all"):
        if "pull_request" in i:
            continue
        etiquetas = {l["name"] for l in i["labels"]}
        if "historia de usuario" in etiquetas or "historia técnica" in etiquetas:
            tipo = "Historia"
        elif "tarea" in etiquetas:
            tipo = "Tarea"
        elif "prueba QA" in etiquetas:
            tipo = "QA"
        elif "defecto" in etiquetas:
            tipo = "Defecto"
        else:
            continue
        ISSUES.append({"repo": repo, "n": i["number"], "titulo": i["title"], "url": i["html_url"], "estado": i["state"],
                       "motivo": i.get("state_reason"), "tipo": tipo, "etiquetas": etiquetas,
                       "etapa": (i.get("milestone") or {}).get("title"), "c": campos(i["body"])})

ORDEN = sorted(ETAPAS.values(), key=lambda e: e["inicio"] or e["fin"] or "")
POS = {e["titulo"]: k for k, e in enumerate(ORDEN)}


def de(tipo):
    return [i for i in ISSUES if i["tipo"] == tipo]


H, T, Q, DF = de("Historia"), de("Tarea"), de("QA"), de("Defecto")
H_act = [h for h in H if "Won't" not in h["etiquetas"]]
pts_tot = sum(num(h["c"].get("Puntos")) for h in H_act)
pts_ok = sum(num(h["c"].get("Puntos")) for h in H_act if h["estado"] == "closed")
horas = sum(num(t["c"].get("Horas")) for t in T)
t_ok = sum(1 for t in T if t["estado"] == "closed")
res = Counter(q["c"].get("Resultado") or ("Aprobada" if q["estado"] == "closed" else "Pendiente") for q in Q)
casos = sum(num(q["c"].get("Casos")) for q in Q)


def pct(a, b):
    return f"{(100 * a / b):.0f} %" if b else "—"


def barra(a, b, ancho=20):
    if not b:
        return ""
    llenos = round(ancho * a / b)
    return "█" * llenos + "░" * (ancho - llenos)


# ------------------------------------------------------------------ markdown
L = []
ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
L.append("# Tablero de control · PAEGo (XP)\n")
L.append(f"Generado por GitHub Actions el {ahora} desde los issues y milestones de "
         + " y ".join(f"[{r}](https://github.com/{r})" for r in REPOS)
         + f". Proyecto con vistas y Roadmap: {PROYECTO}\n")

L.append("## Indicadores\n")
L.append("| Indicador | Valor | Avance |")
L.append("|---|---|---|")
L.append(f"| Historias (sin Won't) | {sum(1 for h in H_act if h['estado'] == 'closed')} de {len(H_act)} hechas | {barra(sum(1 for h in H_act if h['estado'] == 'closed'), len(H_act))} {pct(sum(1 for h in H_act if h['estado'] == 'closed'), len(H_act))} |")
L.append(f"| Puntos | {pts_ok:.0f} de {pts_tot:.0f} | {barra(pts_ok, pts_tot)} {pct(pts_ok, pts_tot)} |")
L.append(f"| Tareas | {t_ok} de {len(T)} cerradas | {barra(t_ok, len(T))} {pct(t_ok, len(T))} |")
L.append(f"| Horas registradas | {horas:.0f} h | |")
L.append(f"| Pruebas y QA | {len(Q)} elementos, {casos:.0f} casos | {barra(res['Aprobada'] + res['Corregida'], len(Q))} {pct(res['Aprobada'] + res['Corregida'], len(Q))} |")
L.append(f"| Resultado de QA | {res['Aprobada']} aprobadas · {res['Corregida']} corregidas · {res['Pendiente']} pendientes | |")
L.append(f"| Defectos | {len(DF)} registrados, {sum(1 for d in DF if d['estado'] == 'closed')} corregidos | |")
L.append("")

L.append("## Etapas XP (milestones)\n")
L.append("| Etapa | Fechas | Historias | Puntos hechos / planeados | Tareas | Horas | Avance |")
L.append("|---|---|---|---|---|---|---|")
for e in ORDEN:
    hs = [h for h in H_act if h["etapa"] == e["titulo"]]
    ts = [t for t in T if t["etapa"] == e["titulo"]]
    p_plan = sum(num(h["c"].get("Puntos")) for h in hs)
    p_ok = sum(num(h["c"].get("Puntos")) for h in hs if h["estado"] == "closed")
    tot = e["abiertos"] + e["cerrados"]
    L.append(f"| {e['titulo']} | {e['inicio']} → {e['fin']} | {len(hs)} | {p_ok:.0f} / {p_plan:.0f} | "
             f"{sum(1 for t in ts if t['estado'] == 'closed')}/{len(ts)} | {sum(num(t['c'].get('Horas')) for t in ts):.0f} | "
             f"{barra(e['cerrados'], tot, 10)} {pct(e['cerrados'], tot)} |")
L.append("")

L.append("## Velocidad por iteración\n")
L.append("```mermaid")
L.append("xychart-beta")
L.append('    title "Puntos completados por etapa"')
vel = [(e["titulo"].split(" · ")[0], sum(num(h["c"].get("Puntos")) for h in H_act if h["etapa"] == e["titulo"] and h["estado"] == "closed"))
       for e in ORDEN]
vel = [(k, v) for k, v in vel if v]
L.append("    x-axis [" + ", ".join(f'"{k}"' for k, _ in vel) + "]")
L.append(f'    y-axis "Puntos" 0 --> {max([v for _, v in vel] + [1]) + 4:.0f}')
L.append("    bar [" + ", ".join(f"{v:.0f}" for _, v in vel) + "]")
L.append("```\n")

L.append("## Cronograma (Gantt)\n")
L.append("```mermaid")
L.append("gantt")
L.append("    title PAEGo · ciclo XP")
L.append("    dateFormat YYYY-MM-DD")
L.append("    axisFormat %d %b")
for e in ORDEN:
    L.append(f"    section {e['titulo'].split(' · ')[0]}")
    estado = "done" if e["abiertos"] == 0 else ("active" if (e["inicio"] or "") <= HOY.isoformat() else "")
    nombre = re.sub(r"[:#;]", " ", e["titulo"])
    L.append(f"    {nombre} :{estado + ', ' if estado else ''}{e['inicio']}, {e['fin']}")
    for t in sorted((t for t in T if t["etapa"] == e["titulo"]), key=lambda t: t["c"].get("Cronograma", "")):
        m = re.match(r"(\d{4}-\d{2}-\d{2}) → (\d{4}-\d{2}-\d{2})", t["c"].get("Cronograma", ""))
        if not m:
            continue
        st = "done, " if t["estado"] == "closed" else ""
        L.append(f"    {re.sub(r'[:#;]', ' ', t['titulo'])[:60]} :{st}{m.group(1)}, {m.group(2)}")
L.append("```\n")

L.append("## Pruebas y QA por grupo\n")
grupos = defaultdict(lambda: [0, 0, 0])
for q in Q:
    g = q["c"].get("Grupo") or "Pruebas adicionales"
    grupos[g][0] += 1
    grupos[g][1] += num(q["c"].get("Casos"))
    grupos[g][2] += q["estado"] == "closed"
L.append("| Grupo | Elementos | Casos | Aprobadas |")
L.append("|---|---|---|---|")
for g, (n, c, ok) in grupos.items():
    L.append(f"| {g} | {n} | {c:.0f} | {ok} |")
L.append("")

pend = [i for i in ISSUES if i["estado"] == "open"]
L.append(f"## Pendiente y en curso ({len(pend)})\n")
for i in sorted(pend, key=lambda i: POS.get(i["etapa"], 99)):
    L.append(f"- [{i['titulo']}]({i['url']}) · {i['tipo']} · {i['etapa'] or 'sin etapa'}")
L.append("")

md = "\n".join(L)

if os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
        f.write(md)
if os.environ.get("SALIDA"):
    with open(os.environ["SALIDA"], "w", encoding="utf-8") as f:
        f.write(md)
if os.environ.get("ACTUALIZAR_ISSUE") == "1":
    existentes = [i for i in paginas(f"/repos/{REPO_TABLERO}/issues?state=all&labels=gestión") if i["title"] == TITULO_ISSUE]
    if existentes:
        api(f"/repos/{REPO_TABLERO}/issues/{existentes[0]['number']}", "PATCH", {"body": md})
    else:
        api(f"/repos/{REPO_TABLERO}/issues", "POST", {"title": TITULO_ISSUE, "body": md, "labels": ["gestión"]})
print(f"{len(H)} historias, {len(T)} tareas, {len(Q)} QA, {len(DF)} defectos, {len(ORDEN)} etapas")
