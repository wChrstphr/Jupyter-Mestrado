# Tutorial: Coleta e Processamento de Dados Judiciais

## Visão Geral do Projeto

Este tutorial descreve o processo de coleta, processamento e enriquecimento de dados de processos judiciais do TJCE, incluindo extração de metadados via API, web scraping para informações complementares e inferência de atributos demográficos.

---

## Etapa 1: Coleta de Dados via API Pública

### 1.1 Configuração Inicial

A API pública do DataJud (CNJ) disponibiliza dados estruturados de processos judiciais. Você precisará:

- **Endpoint**: `https://api-publica.datajud.cnj.jus.br/api_publica_tjce/_search`
- **Autenticação**: APIKey fornecida pelo CNJ
- **Biblioteca**: `requests` para requisições HTTP

### 1.2 Estrutura da Requisição

```python
import requests
import json

payload = {
    "size": 10000,  # Máximo de registros por requisição
    "query": {
        "match": {
            "assuntos.codigo": "12487"  # Código do assunto jurídico
        }
    },
    "sort": [{"dataAjuizamento": {"order": "desc"}}]
}
```

**Dica**: A API retorna dados em formato JSON aninhado. Explore a estrutura usando `response.json()` e navegue pelos níveis `hits > hits > _source`.

### 1.3 Dados Importantes a Extrair

- `numeroProcesso`: Identificador único
- `classe.nome`: Tipo de ação judicial
- `orgaoJulgador`: Informações do órgão
- `movimentos`: Array com histórico processual
- `dataAjuizamento`: Data de entrada

**Tarefa**: Implemente uma função que extrai esses campos e os organiza em uma lista de dicionários.

---

## Etapa 2: Processamento com Pandas

### 2.1 Transformação em DataFrame

Converta a lista de processos em um DataFrame do pandas para facilitar análise e filtros:

```python
import pandas as pd

df = pd.DataFrame(processos, columns=['numero_processo', 'classe', ...])
```

### 2.2 Análise de Decisões Judiciais

Os movimentos processuais contêm informações sobre decisões. Você precisa:

1. Iterar sobre o array `movimentos` de cada processo
2. Identificar movimentos que contenham termos como "Procedência" ou "Improcedência"
3. Criar um novo DataFrame relacionando processos e decisões

**Desafio**: Alguns processos têm decisões compostas (ex: "Improcedência do pedido e improcedência do pedido contraposto"). Como tratá-las?

### 2.3 Seleção Estratificada

Para balancear seu dataset, implemente uma estratégia de amostragem:

```python
# Exemplo de seleção em blocos
procedencias = []
tamanho_bloco = 20
pulo = 60
posicao = 0

while len(procedencias) < target_size:
    procedencias.extend(range(posicao, posicao + tamanho_bloco))
    posicao += tamanho_bloco + pulo
```

### 2.4 Exportação

Salve os resultados em múltiplos formatos:
- CSV com números de processos (entrada para web scraping)
- CSV com decisões mapeadas
- JSON com dados completos

---

## Etapa 3: Web Scraping com Playwright

### 3.1 Por que Web Scraping?

A API não fornece informações sobre juízes e partes do processo. Essas informações estão disponíveis apenas no site do e-SAJ do TJCE.

### 3.2 Configuração do Ambiente

```bash
pip install playwright pandas
playwright install chromium
```

### 3.3 Navegação Automatizada

**Estrutura básica**:

```python
from playwright.async_api import async_playwright
import asyncio

async def buscar_dados_processo(page, numero_processo):
    # 1. Navegar para o site do TJCE
    await page.goto("URL_DO_ESAJ")
    
    # 2. Selecionar tipo de busca
    # 3. Preencher número do processo
    # 4. Clicar em Consultar
    # 5. Aguardar carregamento
    # 6. Extrair informações
```

### 3.4 Extração de Dados

**Desafio - Nome do Juiz**:
- Localizar usando seletores CSS: `#juizPrimeiraDivTable span`
- **Alternativa**: Usar regex no HTML quando não há elemento estruturado
- **Problema comum**: Capturar "Juiz de Direito" ao invés do nome
- **Solução**: Implementar validação de nomes capturados

**Desafio - Nome do Requerente**:
- Buscar em tabela de partes: `#tablePartesPrincipais`
- **Atenção**: O termo pode variar ("Requerente", "Autor", "Massa Falida")
- Implementar busca sequencial com fallback

### 3.5 Sistema de Cache

**Crucial para projetos com centenas de processos**:

```python
# Salvar progresso periodicamente
if idx % 50 == 0:
    salvar_cache(resultados)
```

**Benefícios**:
- Retomar coleta após interrupções
- Evitar reprocessamento
- Adicionar novos processos incrementalmente

### 3.6 Tratamento de Erros

Categorize os resultados:
- `sucesso`: Ambos os dados coletados
- `dados_incompletos`: Apenas um campo encontrado
- `nao_encontrado`: Processo inexistente no sistema
- `erro`: Falha na extração

**Importante**: Filtrar processos não encontrados antes de salvar resultados finais.

---

## Etapa 4: Inferência de Sexo com Base de Dados

### 4.1 Fonte de Dados

Utilize bases públicas de nomes brasileiros (ex: IBGE, bases do GitHub). O formato comum é CSV comprimido (`.csv.gz`).

### 4.2 Leitura de Dados Comprimidos

```python
df_nomes = pd.read_csv(
    'nomes.csv.gz',
    compression='gzip',
    encoding='utf-8',
    on_bad_lines='skip'
)
```

**Tarefa**: Identifique as colunas que contêm o nome e a classificação de sexo.

### 4.3 Estratégia de Inferência

1. **Extração do primeiro nome**:
   ```python
   primeiro_nome = nome_completo.strip().split()[0]
   ```

2. **Normalização**: Converter para maiúsculas para matching case-insensitive

3. **Busca no banco**:
   - Se encontrar uma entrada: retornar sexo
   - Se encontrar múltiplas: usar a classificação mais frequente (`.mode()`)
   - Se não encontrar: retornar "Indefinido"

### 4.4 Aplicação em Lote

Use `apply()` do pandas para processar todos os registros:

```python
df['sexo_juiz'] = df['primeiro_nome_juiz'].apply(
    lambda x: buscar_sexo(x, df_nomes, 'coluna_nome', 'coluna_sexo')
)
```

### 4.5 Validação dos Resultados

Após inferência, verifique:
- Distribuição de sexos (`.value_counts()`)
- Taxa de nomes indefinidos
- Amostras para validação manual

---

## Etapa 5: Integração e Resultados Finais

### 5.1 Estrutura Final do Dataset

```csv
id,numero_processo,juiz,sexo_juiz,requerente,sexo_requerente,sentenca_favoravel,status
1,02187331420258060001,Alda Maria Holanda Leite,F,Heverton Araujo Sena de Assis,M,True,sucesso
```

### 5.2 Fluxo Completo de Arquivos

```
API DataJud → dados_completos.json
           ↓
      Pandas Processing
           ↓
      ├─→ processos_completo.csv (todos os dados)
      ├─→ decisoes_resumo.csv (decisões mapeadas)
      └─→ numeros_processos.csv (input para scraping)
                ↓
          Web Scraping
                ↓
      ├─→ cache_processos.json (progresso)
      └─→ dados_processos_tjce.csv (juiz + requerente)
                ↓
         Inferência de Sexo
                ↓
      dados_processos_com_sexo.csv (dataset final)
```

---

## Boas Práticas e Dicas

### Performance
- Use `headless=True` no Playwright para produção
- Implemente delays (`asyncio.sleep()`) entre requisições
- Processe em lotes para economizar memória

### Qualidade dos Dados
- Valide regex antes de aplicar em produção
- Teste com amostras pequenas primeiro
- Mantenha logs de processos problemáticos

### Reprodutibilidade
- Documente versões de bibliotecas (`requirements.txt`)
- Salve dados intermediários
- Use seeds para amostragens aleatórias

### Ética e Legalidade
- Respeite robots.txt e termos de uso
- Não sobrecarregue servidores públicos
- Anonimize dados sensíveis quando necessário

---

## Exercícios Propostos

1. **API**: Modifique a query para buscar processos de múltiplos assuntos
2. **Regex**: Crie padrões para extrair outras informações (comarca, advogados)
3. **Análise**: Calcule estatísticas sobre tempo de tramitação
4. **Visualização**: Crie gráficos mostrando distribuição de sexo vs. decisão
5. **Machine Learning**: Use o dataset para treinar classificadores de decisão

---

## Estrutura de Arquivos do Projeto

```
projeto/
├── coleta_api.py           # Script de coleta via API
├── processar_dados.py      # Processamento com pandas
├── scraper_tjce.py         # Web scraping automatizado
├── inferir_sexo.py         # Inferência demográfica
├── requirements.txt        # Dependências do projeto
├── dados/
│   ├── input/             # Dados brutos
│   └── output/            # Resultados processados
└── cache/                 # Arquivos temporários
```

---

## Referências Técnicas

- **Playwright**: Documentação oficial em https://playwright.dev/python/
- **Pandas**: Guia de processamento de dados
- **API DataJud**: Documentação do CNJ sobre acesso programático
- **Regex em Python**: Padrões para extração de texto

---

**Nota Final**: Este tutorial fornece a estrutura conceitual e técnica necessária. A implementação específica requer adaptação às peculiaridades de cada tribunal e ajuste fino de parâmetros baseado em experimentação.
