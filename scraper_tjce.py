"""
Web Scraper para coletar dados de processos do TJCE
Coleta: Nome do Juiz e Nome do Requerente
"""

import csv
import json
import asyncio
import re
import os
import sys
from playwright.async_api import async_playwright

# Forçar UTF-8 no console Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Constantes
CACHE_FILE = "data/json/cache_processos.json"
# Palavras, padrões e tipos descobertos por tentativa e erro
PALAVRAS_INVALIDAS_JUIZ = ["Especial", "Cível", "Criminal", "Direito", "Vara"]
PADROES_JUIZ = [
    r"Juiz(?:a)?\s+de\s+Direito\s*[:\-]\s*([A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][a-zàáâãçéêíóôõú]+(?:\s+[A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][a-zàáâãçéêíóôõú]+)+)",
    r"Juiz(?:a)?\s*[:\-]\s*([A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][a-zàáâãçéêíóôõú]+(?:\s+[A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][a-zàáâãçéêíóôõú]+)+)",
    r"Juiz(?:a)?[^>]{0,80}?([A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][a-zàáâãçéêíóôõú]{2,}(?:\s+(?:de|da|do|dos|das)\s+[A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][a-zàáâãçéêíóôõú]+|\s+[A-ZÀÁÂÃÇÉÊÍÓÔÕÚ][a-zàáâãçéêíóôõú]{2,})+)",
]
TIPOS_PARTE = ["Requerente", "Autor", "Massa Falida"]


def ler_numeros_processos(arquivo_csv="data/csv/numeros_processos.csv"):
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
        with open("data/csv/decisoes_resumo.csv", "r", encoding="utf-8") as f:
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
    except Exception as e:
        # Se browser foi fechado, propagar exceção
        if "closed" in str(e).lower():
            raise
        # Outros erros de navegação
        print(f"   Erro de navegação: {str(e)}")
        return {
            "numero_processo": numero_processo,
            "juiz": None,
            "requerente": None,
            "status": "erro",
        }

    try:

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
                print("   Processo não encontrado")
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


async def buscar_texto_decisao(page):
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
                    print(
                        f"   Decisão extraída: {texto[:250]}...\nTamanho: {len(texto)} chars"
                    )
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
    numeros_processos = ler_numeros_processos("data/csv/numeros_processos.csv")
    print(f"   Total de processos a buscar: {len(numeros_processos)}")

    # Carregar decisões
    print("\n2. Carregando decisões...")
    decisoes_map = carregar_decisoes()

    # Carregar cache
    print("\n3. Verificando cache...")
    cache_completo = carregar_cache()

    # Pega processos já coletados
    numeros_processos_set = set(numeros_processos)
    resultados = [
        r for r in cache_completo if r["numero_processo"] in numeros_processos_set
    ]

    #
    processos_ja_coletados = {r["numero_processo"] for r in resultados}
    processos_pendentes = [
        num for num in numeros_processos if num not in processos_ja_coletados
    ]

    if not processos_pendentes:
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

        try:
            for idx, numero in enumerate(processos_pendentes, 1):
                total_geral = processos_no_cache + idx
                print(
                    f"\n[{idx}/{len(processos_pendentes)} pendentes | {total_geral}/{len(numeros_processos)} total] Processando {numero}..."
                )

                try:
                    # Buscar dados básicos (juiz e requerente)
                    resultado = await buscar_dados_processo(page, numero)

                    # Se encontrou o processo, buscar também o texto da decisão
                    if resultado["status"] in ["sucesso", "dados_incompletos"]:
                        texto_decisao = await buscar_texto_decisao(page)
                        resultado["texto_decisao"] = texto_decisao
                    else:
                        resultado["texto_decisao"] = None

                    resultados.append(resultado)

                    # Salvar cache a cada 15 processos
                    if idx % 15 == 0:
                        salvar_cache(resultados)

                    # Pausa entre requisições
                    await asyncio.sleep(0.5)

                except Exception as e:
                    # Se browser foi fechado, parar execução
                    if "closed" in str(e).lower():
                        print("\n  Browser fechado")
                        break
                    resultados.append(
                        {
                            "numero_processo": numero,
                            "juiz": None,
                            "requerente": None,
                            "texto_decisao": None,
                            "status": "erro",
                        }
                    )

        finally:
            try:
                await context.close()
                await browser.close()
            except Exception:
                pass

    # Salvar cache final e resultados
    print("\n   Salvando resultados finais...")
    salvar_cache(resultados)
    salvar_resultados_finais(resultados, decisoes_map)

    # Estatísticas
    print("\n" + "-" * 30)
    print("ESTATÍSTICAS")
    print("-" * 30)

    print(f"Total de processos: {len(resultados)}")
    print(f"Sucesso: {sum(1 for r in resultados if r['status'] == 'sucesso')}")
    print(
        f"Não encontrados: {sum(1 for r in resultados if r['status'] == 'nao_encontrado')}"
    )
    print(
        f"Dados incompletos: {sum(1 for r in resultados if r['status'] == 'dados_incompletos')}"
    )
    print(f"Erros: {sum(1 for r in resultados if r['status'] == 'erro')}")



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

        print("    Output gerado:")

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
    with open("data/json/dados_processos_tjce.json", "w", encoding="utf-8") as f:
        json.dump(resultados_completos, f, indent=2, ensure_ascii=False)
    print(
        f"    - Arquivo JSON salvo: dados_processos_tjce.json."
    )

    # Salvar em CSV
    with open(
        "data/csv/dados_processos_tjce.csv", "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "numero_processo",
                "juiz",
                "requerente",
                "texto_decisao",
                "sentenca_favoravel",
                "status",
            ],
        )
        writer.writeheader()
        writer.writerows(resultados_completos)
    print(
        f"    - Arquivo CSV salvo: dados_processos_tjce.csv."
    )


async def executar_pipeline_scraping():
    """
    Executa scraping de dados do TJCE
    """
    await executar_scraping()


if __name__ == "__main__":
    asyncio.run(executar_pipeline_scraping())
