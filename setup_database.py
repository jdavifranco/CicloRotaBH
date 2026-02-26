
"""
Setup do banco de dados para roteamento ciclistico em Belo Horizonte.

Bases de dados:
  - CIRCULACAO_VIARIA.csv       (rede viaria)
  - CURVA_DE_NIVEL_5M.csv       (elevacao)
  - FAIXA_RODAGEM_RODOVIA.csv   (rodovias - penalidade)
  - LOGRADOURO_OBRA_DE_ARTE.csv (viadutos/pontes - penalidade)
"""


import os, sys, time
from pathlib import Path
import psycopg


DB = os.getenv("PGDATABASE", "ciclorota_bh")
USER = os.getenv("PGUSER", "postgres")
PWD = os.getenv("PGPASSWORD", "postgres")
HOST = os.getenv("PGHOST", "localhost")
PORT = os.getenv("PGPORT", "5432")
SRID = 31983
DATA = Path(__file__).parent / "base de dados"

REQUIRED_FILES = [
    "CIRCULACAO_VIARIA.csv",
    "CURVA_DE_NIVEL_5M.csv",
    "FAIXA_RODAGEM_RODOVIA.csv",
    "LOGRADOURO_OBRA_DE_ARTE.csv",
    "ROTA_CICLOVIARIA.csv",
]


# Utilitarios

def log(msg):
    print(msg, flush=True)


def get_conn(dbname=None, autocommit=False):
    return psycopg.connect(
        dbname=dbname or DB, user=USER, password=PWD,
        host=HOST, port=PORT, autocommit=autocommit,
    )


def detect_encoding(path):
    for enc in ["utf-8", "latin-1", "cp1252"]:
        try:
            with open(path, "r", encoding=enc) as f:
                f.read(8192)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return "utf-8"


def load_csv(connection, csv_path, staging_cols, insert_sql):
    """Carrega CSV com geometrias WKT usando staging table + COPY FROM STDIN (FORMAT CSV)."""
    enc = detect_encoding(csv_path)
    cur = connection.cursor()
    cur.execute("SET client_encoding TO 'UTF8'")

    col_defs = ", ".join(f"{c} TEXT" for c in staging_cols)
    cur.execute("DROP TABLE IF EXISTS _stg")
    cur.execute(f"CREATE TEMP TABLE _stg ({col_defs})")

    with open(csv_path, "r", encoding=enc, errors="replace") as f:
        with cur.copy("COPY _stg FROM STDIN WITH (FORMAT CSV, HEADER TRUE)") as copy:
            while chunk := f.read(65536):
                copy.write(chunk.encode("utf-8"))

    connection.commit()
    cur.execute(insert_sql)
    count = cur.rowcount
    connection.commit()
    cur.execute("DROP TABLE IF EXISTS _stg")
    connection.commit()
    return count




def check_files():
    log("[1/9] Verificando arquivos...")
    for f in REQUIRED_FILES:
        path = DATA / f
        assert path.exists(), f"Arquivo nao encontrado: {path}"
    log("  OK")


def create_database():
    log(f"[2/9] Criando banco '{DB}'...")
    c = get_conn("postgres", autocommit=True)
    cur = c.cursor()
    cur.execute(f"SELECT 1 FROM pg_database WHERE datname = '{DB}'")
    if cur.fetchone():
        cur.execute(f"DROP DATABASE {DB} WITH (FORCE)")
    cur.execute(f"CREATE DATABASE {DB}")
    cur.close()
    c.close()
    log("  OK")


def create_extensions():
    log("[3/9] Habilitando PostGIS e pgRouting...")
    c = get_conn()
    cur = c.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    cur.execute("CREATE EXTENSION IF NOT EXISTS pgrouting")
    c.commit()
    cur.close()
    c.close()
    log("  OK")


# 4: Carrega dados dos CSVs

def load_data():
    log("[4/9] Carregando dados...")
    c = get_conn()
    cur = c.cursor()

    # circulacao_viaria
    cur.execute(f"""
        CREATE TABLE circulacao_viaria (
            id_tcv INTEGER PRIMARY KEY,
            tipo_trecho TEXT,
            tipo_logradouro TEXT,
            logradouro TEXT,
            cod_logradouro INTEGER,
            source INTEGER,
            target INTEGER,
            geom GEOMETRY(MULTILINESTRING, {SRID})
        )
    """)
    c.commit()

    n = load_csv(c, DATA / "CIRCULACAO_VIARIA.csv",
        ["fid","id_tcv","tipo_trecho","tipo_logradouro","logradouro",
         "cod_logradouro","source","target","geometria"],
        f"""INSERT INTO circulacao_viaria
            (id_tcv, tipo_trecho, tipo_logradouro, logradouro,
             cod_logradouro, source, target, geom)
            SELECT
                NULLIF(TRIM(id_tcv),'')::INTEGER,
                NULLIF(TRIM(tipo_trecho),''),
                NULLIF(TRIM(tipo_logradouro),''),
                NULLIF(TRIM(logradouro),''),
                NULLIF(TRIM(cod_logradouro),'')::INTEGER,
                NULLIF(TRIM(source),'')::INTEGER,
                NULLIF(TRIM(target),'')::INTEGER,
                ST_GeomFromText(geometria, {SRID})
            FROM _stg
            WHERE geometria IS NOT NULL AND TRIM(geometria) != ''
        """)
    log(f"  circulacao_viaria: {n} registros")

    # curva_nivel_5m
    cur.execute(f"""
        CREATE TABLE curva_nivel_5m (
            id_cn5m INTEGER,
            cota DOUBLE PRECISION,
            geom GEOMETRY(MULTILINESTRING, {SRID})
        )
    """)
    c.commit()

    n = load_csv(c, DATA / "CURVA_DE_NIVEL_5M.csv",
        ["fid","id_cn5m","geometria","cota"],
        f"""INSERT INTO curva_nivel_5m (id_cn5m, cota, geom)
            SELECT
                NULLIF(TRIM(id_cn5m),'')::INTEGER,
                NULLIF(TRIM(cota),'')::DOUBLE PRECISION,
                ST_GeomFromText(geometria, {SRID})
            FROM _stg
            WHERE geometria IS NOT NULL AND TRIM(geometria) != ''
        """)
    log(f"  curva_nivel_5m: {n} registros")

    # faixa_rodagem_rodovia
    cur.execute(f"""
        CREATE TABLE faixa_rodagem_rodovia (
            id_fx_rod INTEGER,
            geom GEOMETRY(MULTILINESTRING, {SRID})
        )
    """)
    c.commit()

    n = load_csv(c, DATA / "FAIXA_RODAGEM_RODOVIA.csv",
        ["fid","id_fx_rod","geometria"],
        f"""INSERT INTO faixa_rodagem_rodovia (id_fx_rod, geom)
            SELECT
                NULLIF(TRIM(id_fx_rod),'')::INTEGER,
                ST_GeomFromText(geometria, {SRID})
            FROM _stg
            WHERE geometria IS NOT NULL AND TRIM(geometria) != ''
        """)
    log(f"  faixa_rodagem_rodovia: {n} registros")

    # logradouro_obra_de_arte
    cur.execute(f"""
        CREATE TABLE logradouro_obra_de_arte (
            id_obrart INTEGER,
            tipo_obra TEXT,
            denominacao TEXT,
            geom GEOMETRY(MULTIPOLYGON, {SRID})
        )
    """)
    c.commit()

    n = load_csv(c, DATA / "LOGRADOURO_OBRA_DE_ARTE.csv",
        ["fid","id_obrart","tipo_obra","denominacao","geometria"],
        f"""INSERT INTO logradouro_obra_de_arte (id_obrart, tipo_obra, denominacao, geom)
            SELECT
                NULLIF(TRIM(id_obrart),'')::INTEGER,
                NULLIF(TRIM(tipo_obra),''),
                NULLIF(TRIM(denominacao),''),
                ST_GeomFromText(geometria, {SRID})
            FROM _stg
            WHERE geometria IS NOT NULL AND TRIM(geometria) != ''
        """)
    log(f"  logradouro_obra_de_arte: {n} registros")

    # rota_cicloviaria
    cur.execute(f"""
        CREATE TABLE rota_cicloviaria (
            id_rota INTEGER,
            nome_lograd TEXT,
            tipo_rota TEXT,
            situacao TEXT,
            geom GEOMETRY(MULTILINESTRING, {SRID})
        )
    """)
    c.commit()

    n = load_csv(c, DATA / "ROTA_CICLOVIARIA.csv",
        ["fid","id_rota","id_trecho","nome_lograd","ano_mes","tipo_rota",
         "posicionamento","extensao","situacao","sentido","largura","segregador","geometria"],
        f"""INSERT INTO rota_cicloviaria (id_rota, nome_lograd, tipo_rota, situacao, geom)
            SELECT
                NULLIF(TRIM(id_rota),'')::INTEGER,
                NULLIF(TRIM(nome_lograd),''),
                NULLIF(TRIM(tipo_rota),''),
                NULLIF(TRIM(situacao),''),
                ST_GeomFromText(geometria, {SRID})
            FROM _stg
            WHERE geometria IS NOT NULL AND TRIM(geometria) != ''
        """)
    log(f"  rota_cicloviaria: {n} registros")

    cur.close()
    c.close()


# 5: Cria indices espaciais

def create_indexes():
    log("[5/9] Criando indices espaciais...")
    c = get_conn()
    cur = c.cursor()
    cur.execute("CREATE INDEX idx_cv_geom ON circulacao_viaria USING GIST(geom)")
    cur.execute("CREATE INDEX idx_cn_geom ON curva_nivel_5m USING GIST(geom)")
    cur.execute("CREATE INDEX idx_rod_geom ON faixa_rodagem_rodovia USING GIST(geom)")
    cur.execute("CREATE INDEX idx_oa_geom ON logradouro_obra_de_arte USING GIST(geom)")
    cur.execute("CREATE INDEX idx_rc_geom ON rota_cicloviaria USING GIST(geom)")
    c.commit()
    cur.close()
    c.close()
    log("  OK")


# 6: Constroi rede de roteamento

def build_network():
    log("[6/9] Construindo rede de roteamento...")
    c = get_conn()
    cur = c.cursor()

    # Cria tabela de arestas
    cur.execute(f"""
        CREATE TABLE rede (
            id SERIAL PRIMARY KEY,
            tipo_logradouro TEXT,
            logradouro TEXT,
            comprimento DOUBLE PRECISION,
            elev_source DOUBLE PRECISION DEFAULT 0,
            elev_target DOUBLE PRECISION DEFAULT 0,
            eh_rodovia BOOLEAN DEFAULT FALSE,
            eh_obra_arte BOOLEAN DEFAULT FALSE,
            eh_ciclovia BOOLEAN DEFAULT FALSE,
            cost DOUBLE PRECISION,
            reverse_cost DOUBLE PRECISION,
            source INTEGER,
            target INTEGER,
            the_geom GEOMETRY(LINESTRING, {SRID})
        )
    """)
    c.commit()

    # Converte MULTILINESTRING para LINESTRING
    cur.execute(f"""
        INSERT INTO rede (tipo_logradouro, logradouro, comprimento, cost, reverse_cost, the_geom)
        SELECT
            tipo_logradouro,
            logradouro,
            ST_Length(sub.geom),
            ST_Length(sub.geom),
            ST_Length(sub.geom),
            sub.geom
        FROM (
            SELECT tipo_logradouro, logradouro,
                   (ST_Dump(ST_LineMerge(geom))).geom AS geom
            FROM circulacao_viaria
            WHERE geom IS NOT NULL
        ) sub
        WHERE ST_GeometryType(sub.geom) = 'ST_LineString'
          AND ST_Length(sub.geom) > 0
    """)
    c.commit()

    cur.execute("SELECT COUNT(*) FROM rede")
    log(f"  {cur.fetchone()[0]} arestas (LINESTRING)")

    # Extrai vertices da rede
    log("  Extraindo vertices (pgr_extractVertices)...")
    cur.execute("""
        SELECT * INTO rede_vertices_pgr
        FROM pgr_extractVertices('SELECT id, the_geom AS geom FROM rede ORDER BY id')
    """)
    c.commit()

    # Preenche source
    log("  Preenchendo source/target...")
    cur.execute("""
        WITH out_going AS (
            SELECT id AS vid, unnest(out_edges) AS eid
            FROM rede_vertices_pgr
        )
        UPDATE rede SET source = vid
        FROM out_going WHERE rede.id = eid
    """)
    c.commit()

    # Preenche target
    cur.execute("""
        WITH in_coming AS (
            SELECT id AS vid, unnest(in_edges) AS eid
            FROM rede_vertices_pgr
        )
        UPDATE rede SET target = vid
        FROM in_coming WHERE rede.id = eid
    """)
    c.commit()

    # Adiciona elevacao aos vertices
    cur.execute("ALTER TABLE rede_vertices_pgr ADD COLUMN elevacao DOUBLE PRECISION DEFAULT 0")
    c.commit()

    # Ajusta SRID da geometria dos vertices
    cur.execute(f"""
        ALTER TABLE rede_vertices_pgr
        ALTER COLUMN geom TYPE GEOMETRY(POINT, {SRID})
        USING ST_SetSRID(geom, {SRID})
    """)
    c.commit()

    cur.execute("CREATE INDEX idx_rede_geom ON rede USING GIST(the_geom)")
    cur.execute("CREATE INDEX idx_rede_src ON rede (source)")
    cur.execute("CREATE INDEX idx_rede_tgt ON rede (target)")
    cur.execute("CREATE INDEX idx_rv_geom ON rede_vertices_pgr USING GIST(geom)")
    c.commit()

    cur.execute("ANALYZE rede")
    cur.execute("ANALYZE rede_vertices_pgr")
    c.commit()

    cur.execute("SELECT COUNT(*) FROM rede_vertices_pgr")
    n_v = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM rede WHERE source IS NOT NULL AND target IS NOT NULL")
    n_e = cur.fetchone()[0]
    log(f"  {n_v} vertices, {n_e} arestas com topologia")

    cur.close()
    c.close()


# 7: Classifica arestas

def classify_edges():
    log("[7/9] Classificando restricoes (rodovia, obra de arte)...")
    c = get_conn()
    cur = c.cursor()

    # Marca arestas em rodovia
    cur.execute("""
        UPDATE rede r SET eh_rodovia = TRUE
        WHERE EXISTS (
            SELECT 1 FROM faixa_rodagem_rodovia rod
            WHERE ST_DWithin(r.the_geom, rod.geom, 10)
        )
    """)
    n_rod = cur.rowcount
    c.commit()

    # Marca arestas em obra de arte
    cur.execute("""
        UPDATE rede r SET eh_obra_arte = TRUE
        WHERE EXISTS (
            SELECT 1 FROM logradouro_obra_de_arte oa
            WHERE ST_Intersects(r.the_geom, oa.geom)
        )
    """)
    n_oa = cur.rowcount
    c.commit()

    log(f"  {n_rod} arestas em rodovia")
    log(f"  {n_oa} arestas em obra de arte")

    # Marca arestas em ciclovia
    cur.execute("""
        UPDATE rede r SET eh_ciclovia = TRUE
        WHERE EXISTS (
            SELECT 1 FROM rota_cicloviaria rc
            WHERE ST_DWithin(r.the_geom, rc.geom, 10)
        )
    """)
    n_rc = cur.rowcount
    c.commit()
    log(f"  {n_rc} arestas em ciclovia")

    cur.close()
    c.close()


# 8: Interpola elevacao

def interpolate_elevation():
    log("[8/9] Interpolando elevacao...")
    c = get_conn()
    cur = c.cursor()

    # Extrai pontos das curvas de nivel
    t1 = time.time()
    cur.execute("""
        CREATE TABLE pontos_elev AS
        SELECT cota, (ST_DumpPoints(geom)).geom AS geom
        FROM curva_nivel_5m
        WHERE cota IS NOT NULL AND geom IS NOT NULL
    """)
    c.commit()

    cur.execute("SELECT COUNT(*) FROM pontos_elev")
    log(f"  {cur.fetchone()[0]} pontos de elevacao extraidos ({time.time()-t1:.0f}s)")

    cur.execute("CREATE INDEX idx_pe_geom ON pontos_elev USING GIST(geom)")
    c.commit()

    # Associa a cota mais proxima a cada vertice
    t1 = time.time()
    cur.execute("""
        UPDATE rede_vertices_pgr v SET elevacao = sub.cota
        FROM (
            SELECT v2.id, p.cota
            FROM rede_vertices_pgr v2
            CROSS JOIN LATERAL (
                SELECT cota FROM pontos_elev p ORDER BY p.geom <-> v2.geom LIMIT 1
            ) p
        ) sub
        WHERE v.id = sub.id
    """)
    c.commit()
    log(f"  {cur.rowcount} vertices com elevacao ({time.time()-t1:.0f}s)")

    cur.execute("SELECT MIN(elevacao), MAX(elevacao) FROM rede_vertices_pgr WHERE elevacao > 0")
    mn, mx = cur.fetchone()
    log(f"  Elevacao: {mn:.0f}m - {mx:.0f}m")

    # Propaga elevacao para as arestas
    cur.execute("""
        UPDATE rede r SET elev_source = vs.elevacao, elev_target = vt.elevacao
        FROM rede_vertices_pgr vs, rede_vertices_pgr vt
        WHERE r.source = vs.id AND r.target = vt.id
    """)
    c.commit()
    log(f"  {cur.rowcount} arestas com elevacao propagada")

    cur.close()
    c.close()


# 9: Calcula custos

def calculate_costs():
    log("[9/9] Calculando custos...")
    c = get_conn()
    cur = c.cursor()

    # Calcula custo e custo reverso
    cur.execute("""
        UPDATE rede SET
            cost = GREATEST(comprimento, 0.1)
                * CASE
                    WHEN elev_source > 0 AND elev_target > 0 AND comprimento > 0 THEN
                        CASE
                            WHEN elev_target > elev_source THEN
                                1.0 + POWER((elev_target - elev_source) / comprimento * 100.0 / 8.0, 2)
                            ELSE
                                GREATEST(0.4, 1.0 - (elev_source - elev_target) / comprimento * 100.0 / 25.0)
                        END
                    ELSE 1.0
                  END
                * CASE WHEN eh_rodovia THEN 100.0 ELSE 1.0 END
                * CASE WHEN eh_obra_arte THEN 50.0 ELSE 1.0 END
                * CASE WHEN eh_ciclovia THEN 0.0 ELSE 1.0 END,
            reverse_cost = GREATEST(comprimento, 0.1)
                * CASE
                    WHEN elev_source > 0 AND elev_target > 0 AND comprimento > 0 THEN
                        CASE
                            WHEN elev_source > elev_target THEN
                                1.0 + POWER((elev_source - elev_target) / comprimento * 100.0 / 8.0, 2)
                            ELSE
                                GREATEST(0.4, 1.0 - (elev_target - elev_source) / comprimento * 100.0 / 25.0)
                        END
                    ELSE 1.0
                  END
                * CASE WHEN eh_rodovia THEN 100.0 ELSE 1.0 END
                * CASE WHEN eh_obra_arte THEN 50.0 ELSE 1.0 END
                * CASE WHEN eh_ciclovia THEN 0.0 ELSE 1.0 END
    """)
    c.commit()

    cur.execute("SELECT COUNT(*) FROM rede WHERE elev_source != elev_target AND elev_source > 0")
    n_elev = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM rede WHERE eh_rodovia")
    n_rod = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM rede WHERE eh_obra_arte")
    n_oa = cur.fetchone()[0]
    log(f"  {n_elev} arestas com desnivel")
    cur.execute("SELECT COUNT(*) FROM rede WHERE eh_ciclovia")
    n_rc = cur.fetchone()[0]


    cur.close()
    c.close()


def main():
    t0 = time.time()
    log("\n=== CICLOROTA BH - SETUP ===\n")

    check_files()
    create_database()
    create_extensions()
    load_data()
    create_indexes()
    build_network()
    classify_edges()
    interpolate_elevation()
    calculate_costs()

    log(f"\n=== CONCLUIDO em {time.time()-t0:.0f}s ===")
    log("Rode: python app.py")
    log("Acesse: http://localhost:5000\n")


if __name__ == "__main__":
    main()
