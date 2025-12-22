# 📘 Trabalho Final — Deep Learning e Processamento de Linguagem Natural (PNL)

Este repositório contém o projeto final da disciplina de **Deep Learning e Processamento de Linguagem Natural**, cujo objetivo é investigar a seguinte pergunta de pesquisa:

> **Há diferença de sentimento na sentença de juízes e juízas no Brasil?**

O estudo utiliza **dados reais do Tribunal de Justiça do Estado do Ceará (TJCE)**, coletados via **API Pública do CNJ (DataJud)** e técnicas de **web scraping**, aplicando modelos modernos de **PLN**, **LLMs** e **testes estatísticos**.

---

## 🧠 Visão Geral do Projeto

O pipeline do projeto é estruturado em quatro etapas principais:

1. Coleta de processos judiciais via API do CNJ (DataJud)
2. Download dos PDFs das decisões judiciais
3. Extração e tratamento da parte decisória dos textos
4. Análise de sentimento, visualização e testes estatísticos

---

## 🚀 Primeiros Passos

### 1. Clonar o repositório

```bash
git clone https://github.com/seu-usuario/seu-repositorio.git
cd seu-repositorio
```

---

### 2. Executar o Notebook 1 — Coleta de Processos
Este notebook é responsável por:

- Consultar a **API Pública do CNJ (DataJud)**;
- Filtrar processos do TJCE por assunto;
- Armazenar metadados dos processos (número);
- Salvar os arquivos intermediários em `data/notebook1/`.

> 🔎 Observação  
> Para evitar sobrecarga do servidor, o processo de coleta adota `time.sleep(0.5)` entre requisições, seguindo boas práticas de scraping responsável.

---

## 📄 Scraping dos PDFs e Extração das Decisões

Para obtenção do texto integral das sentenças e deve ser executada **após a conclusão do Notebook 1**.

### 3. Preparação do ambiente

Acesse a pasta raiz do projeto pelo terminal ou VS Code e crie um ambiente virtual:

```bash
python -m venv venv
```

Ative o ambiente virtual:

- **Windows**
```bash
venv\Scripts\activate
```

- **Linux / macOS**
```bash
source venv/bin/activate
```

Instale as dependências necessárias:

```bash
pip install -r requirements.txt
```

---

### 4. Download dos PDFs das decisões

Execute o scraper responsável pelo download dos arquivos PDF:

```bash
python scraper_pdf_tjce.py
```

Este script:
- Utiliza o arquivo gerado no notebook `numeros_processo.csv`;
- Acessa a página individual de cada processo;
- Tenta localizar o link da decisão judicial;
- Realiza o download do PDF quando disponível;
- Registra falhas nos casos de:
  - segredo de justiça,
  - inexistência de PDF,
  - processos não localizados.

Os PDFs válidos são armazenados localmente para a etapa seguinte.

---

### 5. Extração da parte decisória

Após o download dos PDFs, execute o script de extração textual:

```bash
python extrator_decisoes.py
```

Este script:

- Lê os PDFs baixados na pasta `/decisoes/*.pdf`;
- Extrai o texto completo da sentença;

Os resultados são salvos em:

```text
data/notebook1/
```

---

### 6. Executar o Notebook 2 — Análises

Abra e execute o notebook:

```text
Notebook_2_Analises.ipynb
```

Este notebook contempla:

- Extração de entidades (nome da parte e título do juiz) com **NER + regex**;
- Inferência de gênero do juiz e da parte com **zero-shot classification**;
- Classificação das sentenças em **procedentes** ou **improcedentes**;
- Pré-processamento textual para uso em LLMs;
- Análise de sentimento com múltiplos modelos:
  - Mixtral
  - GPT-OSS
  - GPT-4o-mini
  - LLaMA 3.3
  - DeepSeek
  - Grok
- Análise de sentimento com **BERT (512 tokens)**;
- Visualizações, heatmaps e estatísticas descritivas;
- Testes estatísticos (t de Welch e χ²).

---

## 📊 Resultados

Ao final da execução:

- Todos os dados tratados, tabelas e gráficos estarão disponíveis em:
  ```text
  data/notebook2/
  ```

---

## 👥 Autoria

Projeto desenvolvido como **Trabalho Final da disciplina de Deep Learning e Processamento de Linguagem Natural (PNL)**, conforme diretrizes acadêmicas pelos integrantes Giovanni Brigido, Analécia Rorato e Paulo Ceser.

