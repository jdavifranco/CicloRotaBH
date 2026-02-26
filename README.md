# CicloRota BH - Roteamento Ciclístico com Banco de Dados Geográfico

Sistema de cálculo de rotas otimizadas para ciclistas em Belo Horizonte, utilizando banco de dados geográfico (PostgreSQL + PostGIS + pgRouting).

A rota é calculada com base em um custo ponderado que considera:
- **Declividade** 
- **Faixa de rodagem de rodovia** 
- **Viadutos, pontes e passarelas** 
- **Rotas cicloviárias** 

## Pré-requisitos

1. **Python 3.8+**
2. **PostgreSQL 14+** com as extensões:
   - **PostGIS 3+** 
   - **pgRouting 3+** 


## Instalação

### 1. Instalar dependências Python

```bash
pip install -r requirements.txt
```

### 2. Configurar credenciais do banco (opcional)

Por padrão, os scripts usam:
- **Banco**: `ciclorota_bh`
- **Usuário**: `postgres`
- **Senha (setup_database.py)**: `postgres`
- **Senha (app.py)**: `203695`
- **Host**: `localhost:5432`



### 3. Executar o setup do banco de dados

```bash
python setup_database.py
```

Este script irá:
- Criar o banco de dados `ciclorota_bh`
- Habilitar PostGIS e pgRouting
- Importar os 5 CSVs da pasta `base de dados/`
- Construir a rede de roteamento com custos ponderados
- Criar índices espaciais e tabela de vértices

As base de dados das curvas de nível e circulacao viária são muito pesadas para subir no github, mas podem ser baixadas nos links abaixo
Circulação Viária: https://geoservicos.pbh.gov.br/geoserver/wfs?service=WFS&version=1.0.0&request=GetFeature&typeName=ide_bhgeo:CIRCULACAO_VIARIA&srsName=EPSG:31983&outputFormat=csv

Curvas de Nível 5M: https://geoservicos.pbh.gov.br/geoserver/wfs?service=WFS&version=1.0.0&request=GetFeature&typeName=ide_bhgeo:CURVA_DE_NIVEL_5M&srsName=EPSG:31983&outputFormat=csv

O processo leva alguns minutos dependendo do hardware.

### 4. Iniciar a aplicação

```bash
python app.py
```

### 5. Acessar o mapa

Abra o navegador em: **http://localhost:5000**

## Uso

1. **Visualize as camadas** no mapa (ciclovias, circulação viária, rodovias, obras de arte)
2. **Clique no mapa** para definir o ponto de **origem** (marcador verde)
3. **Clique novamente** para definir o ponto de **destino** (marcador vermelho)
4. **Clique em calcular rota** para obter:
   - **Rota segura** (usa custo ponderado com elevação e penalidades)
   - **Rota rápida** (prioriza menor distância)
5. A rota é exibida com cores indicando o tipo de trecho:
   - Verde: ciclovia
   - Azul: via normal (baixa declividade)
   - Amarelo/laranja: declividade moderada a alta
   - Vermelho: declividade forte


## Função de Custo

O custo da **rota segura** é calculado no `setup_database.py` com base em:

```
cost = comprimento
  × fator_declividade_direta
  × 100  se rodovia
  × 50   se obra de arte
  × 0.0  se ciclovia

reverse_cost = comprimento
  × fator_declividade_reversa
  × 100  se rodovia
  × 50   se obra de arte
  × 0.0  se ciclovia
```

Onde o fator de declividade:
- Penaliza fortemente **subidas** (termo quadrático)
- Dá bônus limitado em **descidas** (com piso mínimo)
- Considera o sentido do trecho (`cost` e `reverse_cost`)

Já a **rota rápida** usa `cost = comprimento` (menor distância).

## Tecnologias

- **PostgreSQL + PostGIS**: Banco de dados geográfico
- **pgRouting**: Algoritmo de Dijkstra para cálculo de menor caminho
- **Python + Flask**: API backend
- **Leaflet.js**: Mapa interativo no frontend
- **SIRGAS 2000 / UTM 23S (EPSG:31983)**: Sistema de coordenadas dos dados

## Dados

Os dados são provenientes do portal de dados abertos de Belo Horizonte (PBH).
