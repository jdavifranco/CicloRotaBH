"""
API Flask - CicloRota BH
Roteamento ciclistico com duas rotas: rapida (distancia) e segura (considera elevacao).
"""

import os, traceback
from pathlib import Path
import psycopg
from flask import Flask, jsonify, request, send_from_directory, make_response

DB = os.getenv("PGDATABASE", "ciclorota_bh")
USER = os.getenv("PGUSER", "postgres")
PWD = os.getenv("PGPASSWORD", "postgres")
HOST = os.getenv("PGHOST", "localhost")
PORT = os.getenv("PGPORT", "5432")
SRID = 31983

app = Flask(__name__)
STATIC = Path(__file__).parent / "static"


def get_conn():
    return psycopg.connect(dbname=DB, user=USER, password=PWD, host=HOST, port=PORT)


@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    r.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return r


@app.route("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.route("/api/status")
def status():
    try:
        c = get_conn()
        cur = c.cursor()
        cur.execute("SELECT COUNT(*) FROM rede")
        edges = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM rede_vertices_pgr")
        verts = cur.fetchone()[0]
        cur.close(); c.close()
        return jsonify({"ok": True, "arestas": edges, "vertices": verts})
    except Exception as e:
        return jsonify({"error": str(e)}), 503


def find_vertex(cur, lat, lng):
    cur.execute(f"""
        SELECT id FROM rede_vertices_pgr
        ORDER BY geom <-> ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), {SRID})
        LIMIT 1
    """, (lng, lat))
    row = cur.fetchone()
    return row[0] if row else None


def run_dijkstra(cur, cost_sql, start, end):
    escaped = cost_sql.replace("'", "''")
    cur.execute(f"""
        SELECT di.seq, di.edge,
               r.logradouro, r.tipo_logradouro, r.comprimento,
               r.elev_source, r.elev_target,
               r.eh_rodovia, r.eh_obra_arte, r.eh_ciclovia,
               ST_AsGeoJSON(ST_Transform(r.the_geom, 4326))::json AS geojson
        FROM pgr_dijkstra('{escaped}', %s, %s, directed := true) di
        JOIN rede r ON di.edge = r.id
        ORDER BY di.seq
    """, (start, end))
    return cur.fetchall()


def build_geojson(rows):
    features = []
    dist = 0.0
    subida_total = 0.0
    descida_total = 0.0
    trechos_rodovia = 0
    trechos_obra_arte = 0
    trechos_ciclovia = 0
    dist_rodovia = 0.0
    dist_obra_arte = 0.0
    dist_ciclovia = 0.0
    prev_elev = None

    for seq, edge_id, logr, tipo, comp, es, et, rod, oa, cic, geojson in rows:
        comp = comp or 0
        es = es or 0
        et = et or 0

        if rod:
            trechos_rodovia += 1
            dist_rodovia += comp
        if oa:
            trechos_obra_arte += 1
            dist_obra_arte += comp
        if cic:
            trechos_ciclovia += 1
            dist_ciclovia += comp

        # Ajusta sentido do trecho pela continuidade da rota
        if prev_elev is not None and es > 0 and et > 0:
            if abs(es - prev_elev) <= abs(et - prev_elev):
                ei, ef = es, et
            else:
                ei, ef = et, es
        else:
            ei, ef = es, et

        desnivel = ef - ei
        slope = (desnivel / comp * 100) if comp > 0 else 0
        prev_elev = ef

        if desnivel > 0:
            subida_total += desnivel
        else:
            descida_total += abs(desnivel)

        if geojson:
            features.append({
                "type": "Feature",
                "geometry": geojson,
                "properties": {
                    "seq": seq,
                    "logradouro": logr or "",
                    "tipo": tipo or "",
                    "comprimento": round(comp, 1),
                    "elev_inicio": round(ei, 1),
                    "elev_fim": round(ef, 1),
                    "desnivel": round(desnivel, 1),
                    "inclinacao": round(slope, 1),
                    "eh_rodovia": bool(rod),
                    "eh_obra_arte": bool(oa),
                    "eh_ciclovia": bool(cic),
                },
            })
        dist += comp

    return {
        "rota": {"type": "FeatureCollection", "features": features},
        "resumo": {
            "distancia_m": round(dist, 1),
            "subida_total_m": round(subida_total, 1),
            "descida_total_m": round(descida_total, 1),
            "trechos": len(rows),
            "trechos_rodovia": trechos_rodovia,
            "dist_rodovia_m": round(dist_rodovia, 1),
            "trechos_obra_arte": trechos_obra_arte,
            "dist_obra_arte_m": round(dist_obra_arte, 1),
            "trechos_ciclovia": trechos_ciclovia,
            "dist_ciclovia_m": round(dist_ciclovia, 1),
        },
    }


# Camadas GeoJSON

LAYER_CONFIG = {
    "ciclovia": {
        "sql": """SELECT id_rota, nome_lograd, tipo_rota, situacao,
                         ST_AsGeoJSON(ST_Transform(geom, 4326))::json AS geojson
                  FROM rota_cicloviaria WHERE geom IS NOT NULL""",
        "props": lambda r: {"nome": r[1] or "", "tipo": r[2] or "", "situacao": r[3] or ""},
    },
    "rodovia": {
        "sql": """SELECT id_fx_rod,
                         ST_AsGeoJSON(ST_Transform(geom, 4326))::json AS geojson
                  FROM faixa_rodagem_rodovia WHERE geom IS NOT NULL""",
        "props": lambda r: {"id": r[0]},
    },
    "obra_arte": {
        "sql": """SELECT id_obrart, tipo_obra, denominacao,
                         ST_AsGeoJSON(ST_Transform(geom, 4326))::json AS geojson
                  FROM logradouro_obra_de_arte WHERE geom IS NOT NULL""",
        "props": lambda r: {"tipo": r[1] or "", "nome": r[2] or ""},
    },
}


@app.route("/api/camada/<nome>")
def camada(nome):
    if nome == "circulacao_viaria":
        return _camada_circulacao()

    cfg = LAYER_CONFIG.get(nome)
    if not cfg:
        return jsonify({"error": f"Camada '{nome}' nao existe"}), 404

    try:
        c = get_conn()
        cur = c.cursor()
        cur.execute(cfg["sql"])
        features = []
        for row in cur.fetchall():
            geojson = row[-1]
            if geojson:
                features.append({
                    "type": "Feature",
                    "geometry": geojson,
                    "properties": cfg["props"](row),
                })
        cur.close(); c.close()
        return jsonify({"type": "FeatureCollection", "features": features})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _camada_circulacao():
    """Circulacao viaria filtrada por bounding box (query param bbox=w,s,e,n)."""
    bbox = request.args.get("bbox", "")
    try:
        c = get_conn()
        cur = c.cursor()
        if bbox:
            w, s, e, n = [float(x) for x in bbox.split(",")]
            cur.execute(f"""
                SELECT tipo_logradouro, logradouro,
                       ST_AsGeoJSON(ST_Transform(the_geom, 4326))::json
                FROM rede
                WHERE the_geom && ST_Transform(
                    ST_MakeEnvelope(%s, %s, %s, %s, 4326), {SRID})
            """, (w, s, e, n))
        else:
            cur.execute("""
                SELECT tipo_logradouro, logradouro,
                       ST_AsGeoJSON(ST_Transform(the_geom, 4326))::json
                FROM rede LIMIT 50000
            """)

        features = []
        for tipo, logr, geojson in cur.fetchall():
            if geojson:
                features.append({
                    "type": "Feature",
                    "geometry": geojson,
                    "properties": {"tipo": tipo or "", "logradouro": logr or ""},
                })
        cur.close(); c.close()
        return jsonify({"type": "FeatureCollection", "features": features})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


SQL_SEGURA = "SELECT id, source, target, cost, reverse_cost FROM rede"
SQL_RAPIDA = "SELECT id, source, target, GREATEST(comprimento,0.1) AS cost, GREATEST(comprimento,0.1) AS reverse_cost FROM rede"


@app.route("/api/rota", methods=["POST", "OPTIONS"])
def rota():
    if request.method == "OPTIONS":
        return make_response("", 204)

    data = request.get_json()
    if not data or "origem" not in data or "destino" not in data:
        return jsonify({"error": "Envie origem e destino"}), 400

    try:
        lat_o, lng_o = float(data["origem"][0]), float(data["origem"][1])
        lat_d, lng_d = float(data["destino"][0]), float(data["destino"][1])
    except (TypeError, ValueError, IndexError):
        return jsonify({"error": "Coordenadas invalidas"}), 400

    try:
        c = get_conn()
        cur = c.cursor()

        v_start = find_vertex(cur, lat_o, lng_o)
        v_end = find_vertex(cur, lat_d, lng_d)

        if not v_start or not v_end:
            return jsonify({"error": "Pontos fora da rede viaria"}), 404
        if v_start == v_end:
            return jsonify({"error": "Origem e destino muito proximos"}), 400

        rows_segura = run_dijkstra(cur, SQL_SEGURA, v_start, v_end)
        rows_rapida = run_dijkstra(cur, SQL_RAPIDA, v_start, v_end)

        cur.close(); c.close()

        if not rows_segura and not rows_rapida:
            return jsonify({"error": "Rota nao encontrada"}), 404

        result = {}
        if rows_segura:
            s = build_geojson(rows_segura)
            result["segura"] = s["rota"]
            result["resumo_segura"] = s["resumo"]
        if rows_rapida:
            r = build_geojson(rows_rapida)
            result["rapida"] = r["rota"]
            result["resumo_rapida"] = r["resumo"]

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print(f"\n  CicloRota BH | http://localhost:5000\n")
    app.run(host="0.0.0.0", port=5000, debug=True)
