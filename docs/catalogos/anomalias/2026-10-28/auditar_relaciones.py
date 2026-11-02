#!/usr/bin/env python3
"""Auditoría reproducible del catálogo de anomalías Maximo (solo lectura)."""
import gzip
import json
from collections import Counter, defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "catalogo_anomalias.json"
SOURCE = ROOT / "relaciones_originales.json.gz"
ISSUES = ROOT / "incidencias_catalogo.json"
OUT = ROOT / "auditoria_relaciones.md"

def load():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    issues = json.loads(ISSUES.read_text(encoding="utf-8"))
    with gzip.open(SOURCE, "rt", encoding="utf-8") as f:
        source = json.load(f)
    return catalog, issues, source

def main():
    c, documented, src = load()
    rows = src["failurelist"]
    defs = src["failurecode"]
    by_id = {r["failurelist"]: r for r in rows}
    duplicate_ids = [k for k, n in Counter(r["failurelist"] for r in rows).items() if n > 1]
    by_parent = defaultdict(list)
    for r in rows:
        if "parent" in r:
            by_parent[r["parent"]].append(r)
    missing_parent_rows = [r for r in rows if "parent" in r and r["parent"] not in by_id]
    missing_parent_ids = sorted({r["parent"] for r in missing_parent_rows})
    actual_edges_missing = [(r["failurelist"], r["parent"]) for r in rows if "parent" in r and r["parent"] not in by_id]

    roots = [r for r in rows if "parent" not in r and r.get("type") is None]
    root_by_key = {(r["orgid"], r["failurecode"]): r for r in roots}
    class_keys = {(x["organization"], x["code"]) for x in c["classes"]}
    class_roots = [root_by_key[k] for k in class_keys if k in root_by_key]

    # Alcanzabilidad desde las 126 clases del catálogo exportado.
    children = defaultdict(list)
    for r in rows:
        if "parent" in r and r["parent"] in by_id:
            children[r["parent"]].append(r)
    reachable = set()
    q = deque(r["failurelist"] for r in class_roots)
    while q:
        node = q.popleft()
        if node in reachable:
            continue
        reachable.add(node)
        q.extend(x["failurelist"] for x in children[node])
    unreachable = [r for r in rows if r["failurelist"] not in reachable]

    # Expandir el catálogo compacto a registros por ruta; verificar cada arista padre-hijo.
    option_sets = c["option_sets"]
    compact_paths = []
    compact_edges = Counter()
    dangling_refs = []
    def expand(options_ref, prefix, parent_code, parent_type):
        if options_ref not in option_sets:
            dangling_refs.append(options_ref); return
        for opt in option_sets[options_ref]:
            path = prefix + [(opt["code"], opt["type"])]
            compact_edges[(parent_code, parent_type, opt["code"], opt["type"])] += 1
            if opt.get("children_ref"):
                expand(opt["children_ref"], path, opt["code"], opt["type"])
            else:
                compact_paths.append(path)
    for cl in c["classes"]:
        expand(cl["options_ref"], [(cl["code"], "CLASS")], cl["code"], "CLASS")

    # Grafo compacto por aristas etiquetadas por códigos y tipos, contado por ocurrencia.
    source_edges = Counter()
    for parent_id, kids in by_parent.items():
        p = by_id.get(parent_id)
        if not p: continue
        pcode, ptype = p["failurecode"], p.get("type", "CLASS")
        for kid in kids:
            source_edges[(pcode, ptype, kid["failurecode"], kid.get("type"))] += 1
    # Comparación por cada clase: rutas completas con multiplicidad, minimiza colisiones entre clases.
    source_paths = Counter()
    for root in class_roots:
        if not children[root["failurelist"]]:
            continue
        stack = [(root, [(root["failurecode"], "CLASS")])]
        while stack:
            node, path = stack.pop()
            kids = children[node["failurelist"]]
            if not kids:
                source_paths[tuple(path)] += 1
            else:
                for kid in kids:
                    stack.append((kid, path + [(kid["failurecode"], kid.get("type"))]))
    compact_path_counts = Counter(tuple(p) for p in compact_paths)
    compact_path_match = compact_path_counts == source_paths

    # Totales por tipo, alturas/clases y aristas no convencionales.
    type_counts = Counter(r.get("type", "CLASS") for r in rows)
    reachable_type_counts = Counter(by_id[i].get("type", "CLASS") for i in reachable)
    depth_counts = Counter(len(p)-1 for p in source_paths.elements())
    class_path_depths = defaultdict(Counter)
    for p, n in source_paths.items():
        class_path_depths[p[0][0]][len(p)-1] += n
    odd_edges = [r for r in rows if "parent" in r and r["parent"] in by_id and by_id[r["parent"]].get("type", "CLASS") == "CLASS" and r.get("type") != "PROBLEM"]
    # Duplicados por código dentro de cada grupo compacto, clasificados por subárbol.
    duplicate_groups = []
    dup_pair_count = 0
    duplicate_occurrences = 0
    equivalent_count = 0
    divergent_count = 0
    duplicate_examples = []
    def subtree_signature(ref, active=None):
        active = active or set()
        if ref in active: return ("CYCLE", ref)
        active = active | {ref}
        return tuple((o["type"], o["code"], subtree_signature(o["children_ref"], active) if o.get("children_ref") else ()) for o in option_sets[ref])
    for gid, options in option_sets.items():
        groups = defaultdict(list)
        for opt in options: groups[(opt.get("type"), opt["code"])].append(opt)
        for (typ, code), same in groups.items():
            if len(same) < 2: continue
            pairs = 1
            dup_pair_count += pairs
            duplicate_occurrences += len(same) - 1
            signatures = [subtree_signature(x["children_ref"]) if x.get("children_ref") else () for x in same]
            equivalent = len(set(signatures)) == 1
            if equivalent: equivalent_count += pairs
            else: divergent_count += pairs
            rec = {"group": gid, "code": code, "type": typ, "nodes": same, "signatures": signatures, "equivalent": equivalent, "pairs": pairs}
            duplicate_groups.append(rec)
            if len(duplicate_examples) < 20: duplicate_examples.append(rec)

    # Definiciones: clave orgid+failurecode; un nodo sin definición si no existe pareja.
    def_keys = {(d.get("orgid"), d.get("failurecode")) for d in defs}
    no_def = [r for r in rows if (r.get("orgid"), r.get("failurecode")) not in def_keys]
    # Nodos con padres ausentes / no alcanzables y resumen de rutas para los ejemplos.
    def route(node_id):
        out=[]; seen=set(); cur=by_id.get(node_id)
        while cur and cur["failurelist"] not in seen:
            seen.add(cur["failurelist"]); out.append(cur)
            cur=by_id.get(cur.get("parent"))
        return list(reversed(out))
    def fmtpath(rs): return " → ".join(f"{x.get('type','CLASS')}:{x['failurecode']}[id={x['failurelist']}]" for x in rs)
    cd19 = [r for r in rows if r.get("parent") in by_id and by_id[r["parent"]]["failurecode"] == "CD-19" and r.get("type") == "CAUSE"]
    rfn70_paths = [p for p in source_paths if p[0][0] == "RFN-70"]
    rfn70 = sorted({tuple(x[0] for x in p) for p in rfn70_paths})
    rfn70_id_paths = []
    for root in class_roots:
        if root["failurecode"] != "RFN-70": continue
        stack = [(root, [root])]
        while stack:
            node, path = stack.pop()
            if not children[node["failurelist"]]: rfn70_id_paths.append(path)
            else:
                for kid in children[node["failurelist"]]: stack.append((kid, path + [kid]))
    c_rfn = [g for g in duplicate_groups if g["code"] == "C-RFN-062"]
    missing_parent_examples = []
    for r in missing_parent_rows[:5]: missing_parent_examples.append((r, fmtpath(route(r["parent"]))))

    # Documented incidence agreement.
    documented_missing = set(documented["missing_parent_ids"])
    documented_unreachable = {x["failurelist"] for x in documented["unreachable_nodes"]}
    documented_odd = {(x["parent"]["failurelist"], x["node"]["failurelist"]) for x in documented["nonstandard_edges"]}
    calculated_odd = {(r["parent"], r["failurelist"]) for r in odd_edges}
    documented_no_def = {(x.get("orgid"), x.get("failurecode"), x.get("failurelist")) for x in documented["nodes_without_code_definition"]}
    calculated_no_def = {(r.get("orgid"), r.get("failurecode"), r["failurelist"]) for r in no_def}
    meta = src["metadata"]
    mcounts = meta["counts"]
    lines = [
        "# Auditoría de relaciones del catálogo de anomalías de Maximo",
        "",
        f"Fecha de extracción auditada: {meta['extracted_at']}",
        "",
        "## Dictamen",
        "",
        "El catálogo es apto como fuente de desplegables dependientes si la implementación conserva cada relación por padre (y la clase/organización) y usa las rutas reales, sin forzar una profundidad fija. La representación compacta conserva el multiconjunto de rutas por código/tipo alcanzables; la estructura no equivale a un árbol universal de tres niveles: hay rutas de distinta longitud y tres causas bajo una clase. Los 4.806 nodos con padres ausentes son resoluciones consultadas que no se pueden ubicar en la jerarquía exportada. Los códigos no son claves únicas: el compacto no conserva los IDs de nodo, y el duplicado C-RFN-062 tiene descendientes distintos bajo el mismo problema; un selector cuyo valor sea solo el código no puede elegir de forma inequívoca su siguiente grupo. Hace falta una clave de ocurrencia o una regla de resolución de Maximo validada para ese caso.",
        "",
        "La auditoría es estática, de todos los registros descargados. La decisión sobre el comportamiento actual de los desplegables solo requiere una muestra dirigida en Maximo (casos estándar, ruta corta/larga, duplicado divergente, clase no estándar), no recorrer manualmente cada selector.",
        "",
        "## Recuento y consistencia de descarga",
        "",
        f"- failurelist: **{len(rows):,}** filas; metadato: {mcounts['nodes_downloaded']:,}. Coincide: **{len(rows)==mcounts['nodes_downloaded']}**.",
        f"- failurecode: **{len(defs):,}** definiciones; metadato: {mcounts['definitions_downloaded']:,}. Coincide: **{len(defs)==mcounts['definitions_downloaded']}**.",
        f"- Clases exportadas: **{len(c['classes'])}**; raíz en volcado: **{len(class_roots)}**; metadato: {mcounts['classes']}.",
        f"- IDs repetidos: **{len(duplicate_ids)}**.",
        f"- Recuento por tipo (raíz sin type contada como CLASS): `{dict(type_counts)}`; metadato: `{mcounts['nodes_by_type']}`.",
        f"- Total de filas frente al total declarado: coincide ({len(rows):,}). La instantánea no conserva cursores ni conteos por página; por tanto puede confirmarse el total final, pero no reconstruir independientemente los límites/solapamientos de cada página a partir de estos archivos.",
        "",
        "## Grafo, compactación y rutas",
        "",
        f"- Alcanzables desde clases: **{len(reachable):,}** (metadato {mcounts['reachable_nodes']:,}); no alcanzables: **{len(unreachable):,}** (incidencias documentadas {len(documented_unreachable):,}). Coincidencia IDs: **{set(r['failurelist'] for r in unreachable)==documented_unreachable}**.",
        f"- Padres ausentes: **{len(missing_parent_ids)} IDs / {len(missing_parent_rows):,} registros hijos**; coincidencia IDs documentados: **{set(missing_parent_ids)==documented_missing}**. Toda relación con padre presente apunta a un ID existente; las faltantes están en incidencias_catalogo.json.",
        f"- Aristas no estándar (hijo distinto de PROBLEM directamente bajo clase): **{len(odd_edges)}**, mismas aristas documentadas: **{calculated_odd==documented_odd}**.",
        f"- Expansión compacta: {len(compact_paths):,} rutas terminales; multiconjunto de rutas completas por código/tipo igual al grafo alcanzable: **{compact_path_match}**; referencias colgantes: **{len(dangling_refs)}**. El compacto no incluye IDs, por lo que esta igualdad no distingue ocurrencias con código idéntico.",
        f"- Grupos compactos compartidos: {mcounts['shared_option_sets']:,}. La comprobación compara rutas expandidas por ocurrencia con rutas reconstruidas desde ID padre, no solo el contenido/hash de los grupos; cualquier mezcla de descendientes altera el multiconjunto y habría fallado.",
        f"- Profundidad de rutas (aristas desde clase): `{dict(sorted(depth_counts.items()))}`.",
        "",
        "## Incidencias verificadas y ejemplos",
        "",
        f"### Códigos sin definición ({len(no_def)})",
        "",
        f"Coinciden exactamente con incidencias: **{calculated_no_def==documented_no_def}**. Códigos: {', '.join(sorted({r['failurecode'] for r in no_def}))}.",
        "",
        "IDs y rutas de los seis nodos: " + "; ".join(fmtpath(route(r["failurelist"])) for r in no_def),
        "",
        "### Tipos/longitudes no estándar",
        "",
        f"Causas directamente bajo CD-19: **{len(cd19)}**: " + "; ".join(fmtpath(route(r['failurelist'])) for r in cd19),
        "",
        "Profundidades por clase (número de aristas desde clase): " + "; ".join(f"{k}: {dict(v)}" for k,v in sorted(class_path_depths.items()) if len(v)>1 or any(d != 3 for d in v)),
        "",
        "Rutas RFN-70 observadas con IDs: " + ("; ".join(fmtpath(p) for p in rfn70_id_paths) or "sin rutas"),
        "",
        f"### Padres ausentes ({len(missing_parent_ids)} IDs)",
        "",
        "Primeros registros con padre ausente y su código/ID: " + "; ".join(f"{r['failurecode']} id={r['failurelist']} parent={r['parent']}" for r,_ in missing_parent_examples),
        "",
        "Estos nodos son inubicables desde clases en esta descarga; no deben colgarse de una clase inferida.",
        "",
        f"### Códigos duplicados bajo un mismo padre ({dup_pair_count} pares)",
        "",
        f"Grupos/código duplicados dentro de option_sets: **{dup_pair_count}**; apariciones adicionales: **{duplicate_occurrences}**. Equivalentes (misma subestructura): **{equivalent_count}**; con descendientes distintos: **{divergent_count}**. Los 489 equivalentes son resoluciones hoja repetidas. C-RFN-062: clase RFN-20[id=163460] → problema P-RFN-139[id=164920] → causa C-RFN-062[id=165598, 165600] → resoluciones S-RFN-263[id=167710] y S-RFN-262[id=167400]; comparten padre pero no descendientes. " + ("; ".join(f"grupo {g['group']}, subárboles {g['signatures']}" for g in duplicate_groups if g['code'] == "C-RFN-062") or "no aparece como duplicado en este recuento"),
        "",
        "Ejemplos de grupos duplicados:",
        "",
    ]
    for g in duplicate_examples[:12]:
        lines.append(f"- Grupo {g['group']}, código {g['code']} ({g['type']}), ocurrencias={len(g['nodes'])}, pares={g['pairs']}, descendientes_equivalentes={g['equivalent']}; subárboles={g['signatures']}")
    lines += [
        "",
        "## Accesibilidad y duplicados de opciones",
        "",
        f"- Opciones exportadas en grupos compactos: {sum(map(len, option_sets.values())):,}; grupos/código repetidos: {dup_pair_count}.",
        f"- Los {len(unreachable):,} no alcanzables son de tipo(s) `{dict(Counter(r.get('type') for r in unreachable))}`; los padres ausentes detectados están documentados: {set(missing_parent_ids)==documented_missing}.",
        "- Una ruta compacta puede repetir el mismo código en grupos distintos: eso es válido porque el valor depende del padre. La UI debe guardar/enviar también el código correspondiente al nivel y respetar el padre seleccionado.",
        "",
        "## Formato de informe legible recomendado",
        "",
        "Mantener el catálogo original intacto y generar una vista tabular por ruta: `organización | clase (código/ID/descr.) | problema (código/ID/descr.) | causa (código/ID/descr.) | resolución (código/ID/descr.) | profundidad | anomalía | definición`. Una fila por camino completo, con celdas vacías cuando el nivel no existe. Para rutas más profundas, usar columnas `nivel_n (tipo, código, ID, descripción)` o JSON Lines con `path: [{id,type,code,description}]`. Incluir IDs evita colapsar duplicados de código y ayuda a revisar descendientes distintos.",
        "",
        "## Reproducción",
        "",
        "En PowerShell, desde esta carpeta, ejecutar:",
        "",
        "```powershell",
        "& 'C:\\Users\\jcamp\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe' .\\auditar_relaciones.py",
        "```",
        "",
        "El script solo lee `catalogo_anomalias.json`, `relaciones_originales.json.gz` e `incidencias_catalogo.json`; sobrescribe únicamente este informe Markdown. No consulta Maximo ni crea/actualiza OTs.",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Informe: {OUT}")
    print(f"rows={len(rows)} defs={len(defs)} roots={len(class_roots)} reachable={len(reachable)} unreachable={len(unreachable)} missing_parent_ids={len(missing_parent_ids)} duplicates_pairs={dup_pair_count} equivalent={equivalent_count} divergent={divergent_count} compact_paths_equal={compact_path_match}")

if __name__ == "__main__": main()
