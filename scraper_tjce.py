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
from urllib.parse import unquote, urlparse, parse_qs

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


async def baixar_pdf_decisao(page, numero_processo, browser):
    """
    Baixa o PDF da sentença do processo.
    
    Args:
        page: Página do Playwright já navegada para o processo
        numero_processo: Número do processo para nome do arquivo
        browser: Instância do browser para obter contexto
    
    Retorna: bool indicando sucesso do download
    """
    try:
        # Expandir movimentações se ainda não expandidas
        link_mais = page.locator("#linkmovimentacoes")
        if await link_mais.is_visible(timeout=2000):
            await link_mais.click()
            await asyncio.sleep(0.5)
        
        # Localizar link do documento "Julgado"
        link = page.locator("xpath=//a[@class='linkMovVincProc' and contains(text(), 'Julgado')]")
        
        # Verificar se o link existe
        if not await link.is_visible(timeout=2000):
            print("   PDF: Link 'Julgado' não encontrado (possível segredo de justiça)")
            return False
        
        url_relativa = await link.get_attribute("href")
        url_completa = "https://esaj.tjce.jus.br" + url_relativa
        
        # Navegar para a página do viewer e aguardar carregamento
        await page.goto(url_completa, wait_until="networkidle")
        await asyncio.sleep(2)
        
        # Extrair URL do PDF do iframe
        iframe = page.locator("iframe")
        if not await iframe.is_visible(timeout=3000):
            print("   PDF: Iframe não encontrado")
            return False
        
        viewer_url = await iframe.get_attribute("src")
        
        # Extrair caminho real do PDF do parâmetro file=
        parsed = urlparse(viewer_url)
        params = parse_qs(parsed.query)
        
        if "file" not in params:
            print("   PDF: Parâmetro 'file' não encontrado na URL do viewer")
            return False
        
        pdf_path = unquote(params["file"][0])
        pdf_url = "https://esaj.tjce.jus.br" + pdf_path
        
        # Baixar PDF mantendo sessão do browser
        os.makedirs("datas", exist_ok=True)
        context = browser.contexts[0]
        response = await context.request.get(pdf_url)
        
        if response.ok:
            pdf_bytes = await response.body()
            # Nome do arquivo: decisao_[numeroProcesso].pdf
            filename = f"datas/decisao_{numero_processo}.pdf"
            with open(filename, "wb") as f:
                f.write(pdf_bytes)
            print(f"   PDF: ✓ Baixado ({len(pdf_bytes)} bytes) -> {filename}")
            return True
        else:
            print(f"   PDF: ✗ Erro HTTP {response.status}")
            return False
        
    except Exception as e:
        print(f"   PDF: Erro ao baixar - {str(e)}")
        return False


async def executar_scraping():
    """Executa o processo de scraping"""
    print("=" * 60)
    print("SCRAPER TJCE - Coleta de Dados de Processos")
    print("=" * 60)

    # Ler números dos processos
    print("\n1. Lendo números dos processos...")
    numeros_processos = ler_numeros_processos("data/csv/numeros_processos.csv")
    print(f"   Total de processos a buscar: {len(numeros_processos)}")

    # Carregar cache
    print("\n2. Verificando cache...")
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
        print("\n3. Salvando resultados finais...")
        salvar_resultados_finais(resultados)
        return

    print(f"   Processos pendentes: {len(processos_pendentes)}")

    # Iniciar scraping
    print("\n3. Iniciando coleta de dados...")

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

                    # Se encontrou o processo, baixar PDF da sentença
                    if resultado["status"] in ["sucesso", "dados_incompletos"]:
                        pdf_baixado = await baixar_pdf_decisao(page, numero, browser)
                        resultado["pdf_baixado"] = pdf_baixado
                    else:
                        resultado["pdf_baixado"] = False

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
                            "pdf_baixado": False,
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
    salvar_resultados_finais(resultados)

    # Estatísticas
    print("\n" + "-" * 30)
    print("ESTATÍSTICAS")
    print("-" * 30)

    print(f"Total de processos: {len(resultados)}")
    print(f"Sucesso: {sum(1 for r in resultados if r['status'] == 'sucesso')}")
    print(f"Não encontrados: {sum(1 for r in resultados if r['status'] == 'nao_encontrado')}")
    print(f"Dados incompletos: {sum(1 for r in resultados if r['status'] == 'dados_incompletos')}")
    print(f"Erros: {sum(1 for r in resultados if r['status'] == 'erro')}")
    print(f"PDFs baixados: {sum(1 for r in resultados if r.get('pdf_baixado', False))}")


def salvar_resultados_finais(resultados):
    """Salva os resultados finais em CSV (posteriormente será adicionado texto extraído dos PDFs)"""
    # Filtrar apenas processos encontrados (sucesso ou dados_incompletos)
    resultados_filtrados = [
        r
        for r in resultados
        if r["status"] not in ["nao_encontrado", "erro"]
    ]

    print(f"    Processos coletados: {len(resultados_filtrados)} de {len(resultados)}")
    print(f"    PDFs baixados: {sum(1 for r in resultados_filtrados if r.get('pdf_baixado', False))}")
    print("\n    Output gerado:")

    # Preparar resultados para CSV (texto_decisao será adicionado posteriormente)
    resultados_completos = [
        {
            "id": idx,
            "numero_processo": resultado["numero_processo"],
            "juiz": resultado.get("juiz"),
            "requerente": resultado.get("requerente"),
            "pdf_baixado": resultado.get("pdf_baixado", False),
            "texto_decisao": "",  # Será preenchido posteriormente com extração dos PDFs
            "status": resultado["status"],
        }
        for idx, resultado in enumerate(resultados_filtrados, 1)
    ]

    # Salvar em JSON
    with open("data/json/dados_processos_tjce.json", "w", encoding="utf-8") as f:
        json.dump(resultados_completos, f, indent=2, ensure_ascii=False)
    print("    - Arquivo JSON salvo: data/json/dados_processos_tjce.json")

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
                "pdf_baixado",
                "texto_decisao",
                "status",
            ],
        )
        writer.writeheader()
        writer.writerows(resultados_completos)
    print("    - Arquivo CSV salvo: data/csv/dados_processos_tjce.csv")


async def executar_pipeline_scraping():
    """
    Executa scraping de dados do TJCE
    """
    await executar_scraping()


if __name__ == "__main__":
    asyncio.run(executar_pipeline_scraping())
