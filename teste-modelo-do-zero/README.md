# Pipeline de Coleta de Dados para Machine Learning

Sistema para coleta e processamento de dados processuais do TJCE.

## 🎯 Início Rápido

### ⚙️ Instalação

### 1. Criar e ativar ambiente virtual

```bash
# Criar
python -m venv venv

# Ativar (Windows)
.\venv\Scripts\activate
```

### 2. Instalar dependências

```bash
pip install -r requirements.txt
playwright install chromium
```
### Passo 1: Coleta Inicial via API

Execute o notebook `notebooks/tjce.ipynb` para:
- Coletar dados da API do TJCE
- Filtrar e balancear processos por decisão
- Gerar arquivos iniciais em `data/`

**O notebook contém instruções detalhadas para os próximos passos.**

### Passo 2: Pipeline de Dados Completo

Após executar o notebook, colete os dados adicionais por webscrapping:

```bash
python coletar_dados_ml.py
```

Este comando executa automaticamente:
1. Web Scraping (juízes e requerentes)
2. Inferência de Sexo
3. Geração de Features (29 features para ML)

## 📁 Estrutura do Projeto

```
Mestrado/
├── notebooks/
│   └── tjce.ipynb               # 1. INÍCIO: Coleta da API e filtros
├── coletar_dados_ml.py          # 2.  Executa pipeline de coleta por meio dos scripts
├── scripts/
│   ├── scraper_tjce.py          # Web Scraping
│   ├── inferir_sexo.py          # Inferência de Sexo
│   └── gerar_features.py        # Geração de Features
├── data/                        # Arquivos de entrada/saída
└── requirements.txt
```

## 🚀 Execução do Pipeline

### Pipeline Completo

```bash
python coletar_dados_ml.py
```

### Etapas Individuais

```bash
# Apenas scraping
python coletar_dados_ml.py --etapa scraping

# Apenas inferência de sexo
python coletar_dados_ml.py --etapa inferir_sexo

# Apenas geração de features
python coletar_dados_ml.py --etapa features
```

## 📊 Sobre as Etapas

### 1. Web Scraping
Coleta dados adicionais do site do TJCE (nome do juiz e requerente).

### 2. Inferência de Sexo
Infere sexo a partir dos nomes usando base de dados brasileiros.

### 3. Geração de Features
Gera dataset final com **29 features** para ML.

## 📂 Arquivos Gerados

**Após notebook:**
- `data/dados_completos.json`
- `data/numeros_processos.csv`
- `data/decisoes_resumo.csv`

**Após pipeline:**
- `data/dados_processos_tjce.csv`
- `data/dados_processos_com_sexo.csv`
- `data/dataset_ml_completo.csv` (29 features)

## 📖 Documentação Completa

Para detalhes técnicos completos sobre as 29 features e funcionamento interno, consulte `docs/README_PIPELINE.md`.

## 📝 Licença

Este projeto é parte de dissertação de mestrado de Giovanni Brigido Bezerra Cardoso.

## 👨‍💻 Autores

Giovanni Brigido Bezerra Cardoso - Mestrado em I.A e Ciência de Dados

Wanjo Christopher Paraizo Escobar - Graduando em Engenharia de Software
