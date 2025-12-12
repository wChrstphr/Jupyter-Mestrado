"""
Scraper para baixar PDFs das sentenças dos processos do TJCE
Baixa apenas os PDFs sem extrair outros dados
"""

import csv
import json
import asyncio
import os
from playwright.async_api import async_playwright
from urllib.parse import unquote, urlparse, parse_qs


def ler_numeros_processos(arquivo_csv="data/csv/numeros_processos.csv"):
    """Lê os números dos processos do arquivo CSV"""
    numeros = []
    with open(arquivo_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            numeros.append(row["numeroProcesso"])
    return numeros


def carregar_cache(cache_file="data/json/cache_pdfs.json"):
    """Carrega lista de PDFs já baixados"""
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
                print(f"   Cache carregado: {len(cache)} PDFs já baixados")
                return set(cache)
        except Exception:
            pass
    return set()


def salvar_cache(pdfs_baixados, cache_file="data/json/cache_pdfs.json"):
    """Salva lista de PDFs baixados"""
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(list(pdfs_baixados), f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"   Erro ao salvar cache: {e}")


async def baixar_pdf_processo(page, numero_processo, browser):
    """
    Baixa o PDF da sentença do processo.
    
    Args:
        page: Página do Playwright
        numero_processo: Número do processo
        browser: Instância do browser
    
    Retorna: bool indicando sucesso do download
    """
    try:
        # Navegar para a página inicial (mais confiável que URL direta)
        await page.goto("https://esaj.tjce.jus.br/cpopg/open.do", wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle", timeout=10000)
        
        # Selecionar opção "Outros"
        radio_outros = page.get_by_role("radio", name="Outros")
        await radio_outros.check()
        await asyncio.sleep(0.3)
        
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
                return False
        except Exception:
            pass
        
        # Expandir movimentações
        link_mais = page.locator("#linkmovimentacoes")
        if await link_mais.is_visible(timeout=2000):
            await link_mais.click()
            await asyncio.sleep(0.8)
        
        # Localizar link do documento da decisão/sentença
        # Busca por diversos tipos de decisões (evitar "Transitado em Julgado")
        link = None
        termos_busca = [
            "starts-with(normalize-space(text()), 'Julgado')",  # Julgado procedente/improcedente
            "starts-with(normalize-space(text()), 'Decisão')",  # Decisão Interlocutória, etc
            "starts-with(normalize-space(text()), 'Sentença')", # Sentença
        ]
        
        for termo in termos_busca:
            locator = page.locator(f"xpath=//a[@class='linkMovVincProc' and {termo}]")
            if await locator.count() > 0:
                link = locator
                break
        
        # Verificar se encontrou algum link
        if link is None or await link.count() == 0:
            print("   Link de decisão não encontrado (segredo de justiça ou sem PDF)")
            return False
        
        # Se houver múltiplos, pegar o primeiro
        if await link.count() > 1:
            print(f"   Múltiplos links ({await link.count()}), usando primeiro")
        
        if not await link.first.is_visible(timeout=2000):
            print("   Link de decisão não visível")
            return False
        
        url_relativa = await link.first.get_attribute("href")
        url_completa = "https://esaj.tjce.jus.br" + url_relativa
        
        # Navegar para a página do viewer
        await page.goto(url_completa, wait_until="networkidle")
        await asyncio.sleep(2)
        
        # Extrair URL do PDF do iframe
        iframe = page.locator("iframe")
        if not await iframe.is_visible(timeout=3000):
            print("   Iframe não encontrado")
            return False
        
        viewer_url = await iframe.get_attribute("src")
        
        # Extrair caminho real do PDF do parâmetro file=
        parsed = urlparse(viewer_url)
        params = parse_qs(parsed.query)
        
        if "file" not in params:
            print("   Parâmetro 'file' não encontrado")
            return False
        
        pdf_path = unquote(params["file"][0])
        pdf_url = "https://esaj.tjce.jus.br" + pdf_path
        
        # Baixar PDF
        os.makedirs("data/decisoes", exist_ok=True)
        context = browser.contexts[0]
        response = await context.request.get(pdf_url)
        
        if response.ok:
            pdf_bytes = await response.body()
            filename = f"data/decisoes/{numero_processo}.pdf"
            with open(filename, "wb") as f:
                f.write(pdf_bytes)
            print(f"   ✓ PDF baixado ({len(pdf_bytes)} bytes)")
            return True
        else:
            print(f"   ✗ Erro HTTP {response.status}")
            return False
        
    except Exception as e:
        if "closed" in str(e).lower():
            raise
        print(f"   Erro: {str(e)}")
        return False


async def executar_scraping():
    """Executa o download dos PDFs"""
    print("=" * 60)
    print("SCRAPER TJCE - Download de PDFs das Sentenças")
    print("=" * 60)
    
    # Ler números dos processos
    print("\n1. Lendo números dos processos...")
    numeros_processos = ler_numeros_processos()
    print(f"   Total de processos: {len(numeros_processos)}")
    
    # Carregar cache
    print("\n2. Verificando cache...")
    cache_file = "data/json/cache_pdfs.json"
    pdfs_baixados = carregar_cache(cache_file)
    
    # Filtrar processos pendentes
    processos_pendentes = [num for num in numeros_processos if num not in pdfs_baixados]
    
    if not processos_pendentes:
        print("\n✓ Todos os PDFs já foram baixados!")
        return
    
    print(f"   Processos pendentes: {len(processos_pendentes)}")
    
    # Iniciar scraping
    print("\n3. Iniciando download dos PDFs...")
    
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        sucessos = 0
        falhas = 0
        
        try:
            for idx, numero in enumerate(processos_pendentes, 1):
                total = len(pdfs_baixados) + idx
                print(f"\n[{idx}/{len(processos_pendentes)} pendentes | {total}/{len(numeros_processos)} total]")
                print(f"Processando {numero}...")
                
                try:
                    sucesso = await baixar_pdf_processo(page, numero, browser)
                    
                    if sucesso:
                        pdfs_baixados.add(numero)
                        sucessos += 1
                    else:
                        falhas += 1
                    
                    # Salvar cache a cada 10 processos
                    if idx % 10 == 0:
                        salvar_cache(pdfs_baixados, cache_file)
                    
                    # Pausa entre requisições
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    if "closed" in str(e).lower():
                        print("\n✗ Browser fechado")
                        break
                    falhas += 1
                    print(f"   Erro: {str(e)}")
        
        finally:
            try:
                await context.close()
                await browser.close()
            except Exception:
                pass
    
    # Salvar cache final
    print("\n4. Salvando cache final...")
    salvar_cache(pdfs_baixados, cache_file)
    
    # Estatísticas
    print("\n" + "-" * 60)
    print("ESTATÍSTICAS")
    print("-" * 60)
    print(f"Total de processos: {len(numeros_processos)}")
    print(f"PDFs já baixados: {len(pdfs_baixados)}")
    print(f"Sucessos nesta execução: {sucessos}")
    print(f"Falhas nesta execução: {falhas}")
    print("-" * 60)


if __name__ == "__main__":
    asyncio.run(executar_scraping())
