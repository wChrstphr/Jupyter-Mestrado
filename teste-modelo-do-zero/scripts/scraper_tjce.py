"""
Web Scraper para coletar dados de processos do TJCE
Coleta: Nome do Juiz e Nome do Requerente

ROADMAP DE FUNÇÕES:
==================

1. LEITURA E PREPARAÇÃO
   ├── ler_numeros_processos()      : Lê CSV com números de processos
   ├── carregar_decisoes()           : Carrega mapeamento de decisões (Procedência/Improcedência)
   ├── carregar_cache()              : Carrega progresso de coletas anteriores
   └── salvar_cache()                : Salva progresso a cada 50 processos

2. VALIDAÇÃO
   └── validar_nome_juiz()           : Valida nomes capturados (remove palavras inválidas)

3. WEB SCRAPING (ASYNC)
   └── buscar_dados_processo()       : Função principal de scraping
       ├── Navega para site do TJCE
       ├── Preenche formulário de busca
       ├── Extrai nome do juiz (tabela ou regex)
       ├── Extrai nome do requerente (fallback: Requerente→Autor→Massa Falida)
       └── Retorna dict com status (sucesso/nao_encontrado/dados_incompletos/erro)

4. PROCESSAMENTO PRINCIPAL
   └── main()                        : Orquestra todo o processo
       ├── Carrega inputs (processos, decisões, cache)
       ├── Identifica processos pendentes
       ├── Inicializa Playwright
       ├── Loop de scraping com progresso
       ├── Salva cache periodicamente
       └── Gera estatísticas finais

5. EXPORTAÇÃO
   └── salvar_resultados_finais()    : Exporta dados coletados
       ├── Filtra processos válidos (remove não encontrados/erros)
       ├── Adiciona campos id e sentenca_favoravel
       ├── Salva JSON (dados_processos_tjce.json)
       └── Salva CSV (dados_processos_tjce.csv)

6. INFERÊNCIA DE SEXO (MÓDULO EXTERNO)
   └── inferir_sexo.py               : Enriquece dados com informação de sexo
       ├── Carrega base de nomes brasileiros
       ├── Extrai primeiro nome de juiz e requerente
       ├── Busca sexo no banco de dados
       └── Salva CSV final (dados_processos_com_sexo.csv)
"""

import csv
import json
import asyncio
import re
import os
from playwright.async_api import async_playwright

# Constantes
CACHE_FILE = "data/output/cache_processos.json"
PALAVRAS_INVALIDAS_JUIZ = ["Especial", "Cível", "Criminal", "Direito", "Vara"]
PADROES_JUIZ = [
    r"Juiz(?:a)?\s+de\s+Direito\s*[:\-]\s*([A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][a-zàáâãçéêíóôõú]+(?:\s+[A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][a-zàáâãçéêíóôõú]+)+)",
    r"Juiz(?:a)?\s*[:\-]\s*([A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][a-zàáâãçéêíóôõú]+(?:\s+[A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][a-zàáâãçéêíóôõú]+)+)",
    r"Juiz(?:a)?[^>]{0,80}?([A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][a-zàáâãçéêíóôõú]{2,}(?:\s+(?:de|da|do|dos|das)\s+[A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][a-zàáâãçéêíóôõú]+|\s+[A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][a-zàáâãçéêíóôõú]{2,})+)",
]
TIPOS_PARTE = ["Requerente", "Autor", "Massa Falida"]


def ler_numeros_processos(arquivo_csv):
    """Lê os números dos processos do arquivo CSV"""
    numeros = []
    with open(arquivo_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            numeros.append(row["numeroProcesso"])
    return numeros


def carregar_decisoes():
    """Carrega o mapeamento de decisões (Procedência/Improcedência)"""
    decisoes_map = {}
    try:
        with open("data/output/decisoes_resumo.csv", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                numero = row["numero_processo"]
                tipo = row["tipo_decisao"]
                # Procedência = True, else False
                sentenca_favoravel = "Procedência" in tipo
                decisoes_map[numero] = sentenca_favoravel
        print(f"   Decisoes carregadas: {len(decisoes_map)} processos")
    except Exception as e:
        print(f"   Erro ao carregar decisoes: {e}")
    return decisoes_map


def carregar_cache():
    """Carrega resultados do cache se existir"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
                print(f"   Cache carregado: {len(cache)} processos ja coletados")
                return cache
        except Exception as e:
            print(f"   Erro ao carregar cache: {e}")
    return []


def salvar_cache(resultados):
    """Salva resultados no cache"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(resultados, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"   Erro ao salvar cache: {e}")


def validar_nome_juiz(nome):
    """Valida se o nome do juiz é válido"""
    if not nome:
        return False
    if re.match(r"^de\s+", nome, re.IGNORECASE):
        return False
    if nome.endswith((" de", " da", " do")):
        return False
    if any(palavra in nome for palavra in PALAVRAS_INVALIDAS_JUIZ):
        return False
    return True


async def buscar_dados_processo(page, numero_processo):
    """
    Busca os dados do processo no site do TJCE
    Retorna: dict com numero_processo, juiz, requerente, status
    """
    try:
        # Navegar para a página inicial
        await page.goto(
            "https://esaj.tjce.jus.br/cpopg/open.do", wait_until="domcontentloaded"
        )
        await page.wait_for_load_state("networkidle")

        # Selecionar opção "Outros"
        radio_outros = page.get_by_role("radio", name="Outros")
        await radio_outros.check()
        await asyncio.sleep(0.5)

        # Preencher o campo de busca
        campo_busca = page.get_by_role("textbox", name="Número do processo")
        await campo_busca.click()
        await campo_busca.fill(numero_processo)

        # Clicar no botão Consultar
        botao_consultar = page.get_by_role("button", name="Consultar")
        await botao_consultar.click()

        # Aguardar carregamento da página de resultado
        await page.wait_for_load_state("networkidle", timeout=15000)

        # Verificar se processo não existe
        try:
            mensagem_erro = page.get_by_text("Não existem informações")
            if await mensagem_erro.is_visible(timeout=2000):
                print(f"   Processo não encontrado")
                return {
                    "numero_processo": numero_processo,
                    "juiz": None,
                    "requerente": None,
                    "status": "nao_encontrado",
                }
        except Exception:
            pass

        # Extrair nome do juiz
        juiz = None
        try:
            # Tentar localizar na tabela
            juiz_element = page.locator("#juizPrimeiraDivTable span").first
            if await juiz_element.is_visible(timeout=2000):
                juiz = (await juiz_element.inner_text()).strip()
        except Exception:
            pass

        # Se não encontrou na tabela, buscar usando regex
        if not juiz:
            try:
                conteudo_html = await page.content()
                for padrao in PADROES_JUIZ:
                    match = re.search(padrao, conteudo_html, re.IGNORECASE)
                    if match:
                        nome_candidato = match.group(1).strip()
                        if validar_nome_juiz(nome_candidato):
                            juiz = nome_candidato
                            break
            except Exception:
                pass

        # Extrair nome do requerente (tenta Requerente, Autor, Massa Falida)
        requerente = None
        for tipo_parte in TIPOS_PARTE:
            try:
                elemento = (
                    page.locator("#tablePartesPrincipais")
                    .locator(f'td:has-text("{tipo_parte}")')
                    .locator("xpath=following-sibling::td[1]")
                )
                if await elemento.is_visible(timeout=2000):
                    texto_completo = await elemento.inner_text()
                    requerente = texto_completo.split("\n")[0].strip()
                    break
            except Exception:
                continue

        # Determinar status
        status = "sucesso" if (juiz and requerente) else "dados_incompletos"

        print(f"   Juiz = {juiz}\n   Requerente = {requerente}")

        return {
            "numero_processo": numero_processo,
            "juiz": juiz,
            "requerente": requerente,
            "status": status,
        }

    except Exception as e:
        print(f"   Erro: {str(e)}")
        return {
            "numero_processo": numero_processo,
            "juiz": None,
            "requerente": None,
            "status": "erro",
        }


async def buscar_texto_decisao(page, numero_processo):
    """
    Busca o texto completo da decisão no site do TJCE.
    O texto está na célula da tabela de movimentos.

    Retorna: str com o texto da decisão ou None se não encontrado
    """
    try:
        # Expandir movimentações completas
        link_mov = page.locator("#linkmovimentacoes")
        if await link_mov.is_visible(timeout=2000):
            await link_mov.click()
            await asyncio.sleep(0.8)

        # Termos de decisão (ordem de prioridade)
        termos = [
            "Julgado procedente o pedido",
            "Julgado improcedente o pedido",
            "Procedência",
            "Improcedência",
        ]

        # Buscar célula com decisão
        for termo in termos:
            celula = page.get_by_role("cell", name=termo)
            if await celula.is_visible(timeout=1000):
                texto = await celula.inner_text()
                if len(texto.strip()) > 50:
                    print(f"   Decisao extraida: {len(texto)} chars")
                    return texto.strip()

        print("   Texto nao encontrado")
        return None

    except Exception as e:
        print(f"   Erro: {str(e)}")
        return None


async def executar_scraping():
    """Executa o processo de scraping"""
    print("=" * 60)
    print("SCRAPER TJCE - Coleta de Dados de Processos")
    print("=" * 60)

    # Ler números dos processos
    print("\n1. Lendo números dos processos...")
    numeros_processos = ler_numeros_processos("data/output/numeros_processos.csv")
    print(f"   Total de processos a buscar: {len(numeros_processos)}")

    # Carregar decisões
    print("\n2. Carregando decisões...")
    decisoes_map = carregar_decisoes()

    # Carregar cache
    print("\n3. Verificando cache...")
    cache_completo = carregar_cache()

    # Filtrar cache apenas para processos da lista atual
    numeros_processos_set = set(numeros_processos)
    resultados = [
        r for r in cache_completo if r["numero_processo"] in numeros_processos_set
    ]

    # Informar se há processos no cache que não estão na lista atual
    processos_ignorados = len(cache_completo) - len(resultados)
    if processos_ignorados > 0:
        print(
            f"   Cache: {len(cache_completo)} processos ({processos_ignorados} ignorados - nao estao na lista atual)"
        )

    processos_ja_coletados = {r["numero_processo"] for r in resultados}
    processos_pendentes = [
        num for num in numeros_processos if num not in processos_ja_coletados
    ]

    if not processos_pendentes:
        print("   Todos os processos ja foram coletados!")
        print("\n4. Salvando resultados finais...")
        salvar_resultados_finais(resultados, decisoes_map)
        return

    print(f"   Processos pendentes: {len(processos_pendentes)}")

    # Iniciar scraping
    print("\n4. Iniciando coleta de dados...")

    async with async_playwright() as playwright:
        # Configurar browser
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # Processar apenas números pendentes
        processos_no_cache = len(resultados)
        for idx, numero in enumerate(processos_pendentes, 1):
            total_geral = processos_no_cache + idx
            print(
                f"\n[{idx}/{len(processos_pendentes)} pendentes | {total_geral}/{len(numeros_processos)} total] Processando {numero}..."
            )

            # Buscar dados básicos (juiz e requerente)
            resultado = await buscar_dados_processo(page, numero)

            # Se encontrou o processo, buscar também o texto da decisão
            if resultado["status"] in ["sucesso", "dados_incompletos"]:
                texto_decisao = await buscar_texto_decisao(page, numero)
                resultado["texto_decisao"] = texto_decisao
            else:
                resultado["texto_decisao"] = None

            resultados.append(resultado)

            # Salvar cache a cada 50 processos
            if idx % 15 == 0:
                salvar_cache(resultados)

            # Pausa entre requisições
            await asyncio.sleep(0.5)

        # Fechar browser
        await context.close()
        await browser.close()

    # Salvar cache final e resultados
    print("\n5. Salvando resultados finais...")
    salvar_cache(resultados)
    salvar_resultados_finais(resultados, decisoes_map)

    # Estatísticas
    print("\n" + "=" * 60)
    print("ESTATÍSTICAS")
    print("=" * 60)

    print(f"Total de processos: {len(resultados)}")
    print(f"Sucesso: {sum(1 for r in resultados if r['status'] == 'sucesso')}")
    print(
        f"Não encontrados: {sum(1 for r in resultados if r['status'] == 'nao_encontrado')}"
    )
    print(
        f"Dados incompletos: {sum(1 for r in resultados if r['status'] == 'dados_incompletos')}"
    )
    print(f"Erros: {sum(1 for r in resultados if r['status'] == 'erro')}")

    print("=" * 60)


def salvar_resultados_finais(resultados, decisoes_map):
    """Salva os resultados finais em JSON e CSV com id, sentenca_favoravel e texto_decisao"""
    # Filtrar apenas processos com sucesso E que tenham texto da decisão
    resultados_filtrados = [
        r
        for r in resultados
        if r["status"] not in ["nao_encontrado", "erro"]
        and r.get("texto_decisao") is not None
    ]

    # Informar quantos processos foram filtrados
    total_coletados = len(
        [r for r in resultados if r["status"] not in ["nao_encontrado", "erro"]]
    )
    processos_sem_texto = total_coletados - len(resultados_filtrados)
    if processos_sem_texto > 0:
        print(
            f"    Filtrados {processos_sem_texto} processos sem texto da decisao (segredo de justica)"
        )
        print(
            f"    Processos com texto: {len(resultados_filtrados)} de {total_coletados} ({len(resultados_filtrados)/total_coletados*100:.1f}%)"
        )

    # Adicionar id e sentenca_favoravel aos resultados
    resultados_completos = [
        {
            "id": idx,
            "numero_processo": resultado["numero_processo"],
            "juiz": resultado.get("juiz"),
            "requerente": resultado.get("requerente"),
            "texto_decisao": resultado.get(
                "texto_decisao"
            ),  # Adicionar texto da decisão
            "sentenca_favoravel": decisoes_map.get(resultado["numero_processo"]),
            "status": resultado["status"],
        }
        for idx, resultado in enumerate(resultados_filtrados, 1)
    ]

    # Salvar em JSON
    with open("data/output/dados_processos_tjce.json", "w", encoding="utf-8") as f:
        json.dump(resultados_completos, f, indent=2, ensure_ascii=False)
    print(
        f"    Arquivo JSON salvo: data/output/dados_processos_tjce.json ({len(resultados_completos)} processos válidos)"
    )

    # Salvar em CSV
    with open(
        "data/output/dados_processos_tjce.csv", "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "numero_processo",
                "juiz",
                "requerente",
                "texto_decisao",  # Adicionar texto da decisão ao CSV
                "sentenca_favoravel",
                "status",
            ],
        )
        writer.writeheader()
        writer.writerows(resultados_completos)
    print(
        f"    Arquivo CSV salvo: data/output/dados_processos_tjce.csv ({len(resultados_completos)} processos válidos)"
    )


async def executar_pipeline_scraping():
    """
    Executa scraping de dados do TJCE
    """
    await executar_scraping()


if __name__ == "__main__":
    asyncio.run(executar_pipeline_scraping())
