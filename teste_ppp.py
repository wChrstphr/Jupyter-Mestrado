from playwright.async_api import async_playwright
from urllib.parse import unquote, urlparse, parse_qs
import asyncio
import os


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # Navegar para a página do processo
        await page.goto("https://esaj.tjce.jus.br/cpopg/show.do?processo.codigo=01002P2X90000&processo.foro=1&processo.numero=0218733-14.2025.8.06.0001")
        
        # Expandir movimentações
        link_mais = page.locator("#linkmovimentacoes")
        if await link_mais.is_visible(timeout=2000):
            await link_mais.click()
            await asyncio.sleep(0.5)
        
        # Localizar link do documento "Julgado"
        link = page.locator("xpath=//a[@class='linkMovVincProc' and contains(text(), 'Julgado')]")
        url_relativa = await link.get_attribute("href")
        url_completa = "https://esaj.tjce.jus.br" + url_relativa
        
        # Navegar para a página do viewer e aguardar carregamento
        await page.goto(url_completa, wait_until="networkidle")
        await asyncio.sleep(2)
        
        # Extrair URL do PDF do iframe
        iframe = page.locator("iframe")
        viewer_url = await iframe.get_attribute("src")
        
        # Extrair caminho real do PDF do parâmetro file=
        parsed = urlparse(viewer_url)
        params = parse_qs(parsed.query)
        pdf_path = unquote(params["file"][0])
        pdf_url = "https://esaj.tjce.jus.br" + pdf_path
        
        # Baixar PDF mantendo sessão do browser
        os.makedirs("datas", exist_ok=True)
        context = browser.contexts[0]
        response = await context.request.get(pdf_url)
        
        if response.ok:
            pdf_bytes = await response.body()
            filename = f"datas/decisao_{url_completa.split('=')[2]}.pdf"
            with open(filename, "wb") as f:
                f.write(pdf_bytes)
            print(f"✓ PDF baixado: {filename} ({len(pdf_bytes)} bytes)")
        else:
            print(f"✗ Erro HTTP: {response.status}")
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
