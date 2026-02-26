# CicloRota BH - Roteamento Ciclístico com Banco de Dados Geográfico

Sistema de cálculo de rotas otimizadas para ciclistas em Belo Horizonte, utilizando banco de dados geográfico (PostgreSQL + PostGIS + pgRouting).

A rota é calculada com base em um custo ponderado que considera:
- **Declividade** do trecho (penaliza trechos íngremes)
- **Faixa de rodagem de rodovia** (evita rodovias)
- **Obras de arte** (evita viadutos, pontes e passarelas sem ciclovia)
- **Rede de priorização de ônibus** (evita faixas exclusivas)
- **Rotas cicloviárias** (prioriza trechos com ciclovia existente)

## Pré-requisitos

1. **Python 3.8+**
2. **PostgreSQL 14+** com as extensões:
   - **PostGIS 3+** (`CREATE EXTENSION postgis`)
   - **pgRouting 3+** (`CREATE EXTENSION pgrouting`)

### Instalação do PostGIS e pgRouting (Windows)

Ao instalar o PostgreSQL, utilize o **Stack Builder** para adicionar as extensões PostGIS e pgRouting. Elas ficam disponíveis na categoria "Spatial Extensions".

## Instalação

### 1. Instalar dependências Python

```bash
pip install -r requirements.txt
```

### 2. Configurar credenciais do banco (opcional)

Por padrão, o sistema usa:
- **Banco**: `ciclorota_bh`
- **Usuário**: `postgres`
- **Senha**: `203695`
- **Host**: `localhost:5432`

Para alterar, defina variáveis de ambiente:

```bash
set PGDATABASE=ciclorota_bh
set PGUSER=postgres
set PGPASSWORD=sua_senha
set PGHOST=localhost
set PGPORT=5432
```

### 3. Executar o setup do banco de dados

```bash
python setup_database.py
```

Este script irá:
- Criar o banco de dados `ciclorota_bh`
- Habilitar PostGIS e pgRouting
- Importar os 7 CSVs da pasta `base de dados/`
- Construir a rede de roteamento com custos ponderados
- Criar índices espaciais e tabela de vértices

O processo leva alguns minutos dependendo do hardware.

### 4. Iniciar a aplicação

```bash
python app.py
```

### 5. Acessar o mapa

Abra o navegador em: **http://localhost:5000**

## Uso

1. **Visualize as camadas** no mapa (ciclovias, faixas de ônibus, rodovias, obras de arte)
2. **Clique no mapa** para definir o ponto de **origem** (marcador verde)
3. **Clique novamente** para definir o ponto de **destino** (marcador vermelho)
4. **Clique em "Calcular rota segura"** para obter a melhor rota para ciclista
5. A rota é exibida com cores indicando o tipo de trecho:
   - Verde: ciclovia
   - Azul: via normal (baixa declividade)
   - Amarelo/laranja: declividade moderada a alta
   - Vermelho: declividade forte

## Estrutura do Projeto

```
trabalho_pratico/
├── base de dados/                 # Dados CSV do portal de dados de BH
│   ├── CIRCULACAO_VIARIA.csv      # Rede viária (231k trechos)
│   ├── DECLIVIDADE_TRECHO_LOGRADOURO_2015.csv
│   ├── LOGRADOURO.csv
│   ├── ROTA_CICLOVIARIA.csv
│   ├── REDE_PRIORIZACAO_ONIBUS.csv
│   ├── LOGRADOURO_OBRA_DE_ARTE.csv
│   └── FAIXA_RODAGEM_RODOVIA.csv
├── static/
│   └── index.html                 # Frontend (Leaflet + mapa interativo)
├── setup_database.py              # Setup do banco de dados
├── app.py                         # API Flask
├── requirements.txt               # Dependências Python
└── README.md                      # Este arquivo
```

## Função de Custo

O custo de cada aresta da rede é calculado como:

```
custo = comprimento
  × (1 + (declividade/10)²)       -- penalidade por declividade
  × 100  se rodovia               -- praticamente bloqueia rodovias
  × 50   se obra de arte          -- evita pontes/viadutos sem ciclovia
  × 5    se faixa de ônibus       -- penaliza faixas exclusivas
  × 0.3  se ciclovia              -- bonifica ciclovias (reduz custo a 30%)
```

## Tecnologias

- **PostgreSQL + PostGIS**: Banco de dados geográfico
- **pgRouting**: Algoritmo de Dijkstra para cálculo de menor caminho
- **Python + Flask**: API backend
- **Leaflet.js**: Mapa interativo no frontend
- **SIRGAS 2000 / UTM 23S (EPSG:31983)**: Sistema de coordenadas dos dados

## Dados

Os dados são provenientes do portal de dados abertos de Belo Horizonte (PBH).
