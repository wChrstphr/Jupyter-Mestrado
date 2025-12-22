import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pdfplumber
import pandas as pd

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# -------------------------------------------------
# 1. Padrões para limpeza de cabeçalho e rodapé
# -------------------------------------------------

HEADER_PATTERNS = [
    r"^PODER JUDICI[ÁA]RIO",
    r"^Comarca de",
    r"^Vara ",
    r"^F[oó]rum",
    r"CEP:\s*\d{5}-\d{3}",
    r"^\s*Tel",
    r"^\s*Email",
]

FOOTER_PATTERNS = [
    r"^Este documento é cópia do original",
    r"^Para conferir o original",
    r"^Documento eletrônico assinado por",
    r"^fls\.\s*\d+",
]

HEADER_REGEXES = [re.compile(p, re.IGNORECASE) for p in HEADER_PATTERNS]
FOOTER_REGEXES = [re.compile(p, re.IGNORECASE) for p in FOOTER_PATTERNS]


def is_header_line(line: str) -> bool:
    """Verifica se uma linha é cabeçalho."""
    line = line.strip()
    if not line:
        return False
    return any(r.search(line) for r in HEADER_REGEXES)


def is_footer_line(line: str) -> bool:
    """Verifica se uma linha é rodapé."""
    line = line.strip()
    if not line:
        return False
    return any(r.search(line) for r in FOOTER_REGEXES)


def merge_lines(lines: List[str]) -> List[str]:
    """
    Junta linhas quebradas em parágrafos, preservando títulos/seções.
    """
    merged = []
    buffer = ""

    sec_pattern = re.compile(
        r"^\d+\.\s*(RELAT[ÓO]RIO|FUNDAMENTA[ÇC][ÃA]O|DISPOSITIVO)\b",
        re.IGNORECASE,
    )

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            # Quebra de parágrafo
            if buffer:
                merged.append(buffer.strip())
                buffer = ""
            continue

        # Se for título de seção, encerra parágrafo e adiciona separado
        if sec_pattern.match(line) or line.isupper():
            if buffer:
                merged.append(buffer.strip())
                buffer = ""
            merged.append(line)
            continue

        # Caso geral: tenta juntar com o buffer anterior
        if not buffer:
            buffer = line
        else:
            if re.search(r"[.!?;:]$", buffer):
                # Buffer termina frase → começa novo parágrafo
                merged.append(buffer.strip())
                buffer = line
            else:
                # Continua a frase
                buffer += " " + line

    if buffer:
        merged.append(buffer.strip())

    return merged


def normalize_paragraphs(merged: List[str]) -> List[str]:
    """Normaliza títulos de seções para formato markdown."""
    normalized = []
    for p in merged:
        p_norm = re.sub(
            r"^\d+\.\s*RELAT[ÓO]RIO\b", "### RELATORIO", p, flags=re.IGNORECASE
        )
        p_norm = re.sub(
            r"^\d+\.\s*FUNDAMENTA[ÇC][ÃA]O\b",
            "### FUNDAMENTACAO",
            p_norm,
            flags=re.IGNORECASE,
        )
        p_norm = re.sub(
            r"^\d+\.\s*DISPOSITIVO\b", "### DISPOSITIVO", p_norm, flags=re.IGNORECASE
        )
        normalized.append(p_norm)
    
    return normalized


# -------------------------------------------------
# 2. Funções de extração de informações
# -------------------------------------------------

def extrair_termo_juiz(text: str) -> Optional[str]:
    """Extrai se é 'juiz' ou 'juiza' do texto."""
    m_termo = re.search(r"Ju[ií]z[ae]\b", text, flags=re.IGNORECASE)
    if m_termo:
        termo = m_termo.group(0).lower()
        termo = termo.replace("í", "i")  # Normaliza 'juíz' → 'juiz'
        return termo
    return None


def extrair_numero_processo(text: str, nome_arquivo: str) -> Optional[str]:
    """
    Extrai o número do processo do texto ou do nome do arquivo.
    Formato esperado: NNNNNNN-DD.AAAA.J.TT.OOOO
    """
    # Padrão 1: Procurar no texto
    padrao_numero = re.compile(
        r"Processo\s+n[º#]:\s*(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})",
        re.IGNORECASE
    )
    m_numero = padrao_numero.search(text)
    
    if m_numero:
        return m_numero.group(1)
    
    # Padrão 2: Extrair do nome do arquivo (formato: NNNNNNNDDAAAAJTTOOOO.pdf)
    # Converter para formato: NNNNNNN-DD.AAAA.J.TT.OOOO
    nome_sem_ext = Path(nome_arquivo).stem
    
    if len(nome_sem_ext) == 20 and nome_sem_ext.isdigit():
        # Formatar: 00004983720188060127 -> 0000498-37.2018.8.06.0127
        numero_formatado = f"{nome_sem_ext[:7]}-{nome_sem_ext[7:9]}.{nome_sem_ext[9:13]}.{nome_sem_ext[13]}.{nome_sem_ext[14:16]}.{nome_sem_ext[16:20]}"
        return numero_formatado
    
    return None


# -------------------------------------------------
# 3. Função principal de extração
# -------------------------------------------------

def extrair_info_pdf(caminho_pdf: str) -> Dict:
    """
    Lê um PDF nativo do TJCE e retorna:
      - arquivo: nome do arquivo
      - numeroProcesso: número do processo
      - texto_completo_limpo: texto principal do documento
      - sucesso: boolean indicando se extração funcionou
      - erro: mensagem de erro (se houver)
    """
    caminho_pdf = Path(caminho_pdf)
    
    resultado = {
        "arquivo": caminho_pdf.name,
        "numeroProcesso": None,
        "texto_completo_limpo": "",
        "sucesso": False,
        "erro": None,
    }

    try:
        # Extrair texto bruto de todas as páginas do PDF
        all_text_pages = []
        cleaned_lines = []

        try:
            with pdfplumber.open(caminho_pdf) as pdf:
                if not pdf.pages:
                    resultado["erro"] = "PDF vazio ou sem páginas"
                    return resultado
                
                for page_idx, page in enumerate(pdf.pages):
                    try:
                        text = page.extract_text() or ""
                        all_text_pages.append(text)

                        for line in text.splitlines():
                            if is_header_line(line) or is_footer_line(line):
                                continue
                            if not line.strip():
                                cleaned_lines.append("")
                            else:
                                cleaned_lines.append(line)
                    except Exception as page_error:
                        logger.warning(f"  Erro ao processar página {page_idx}: {str(page_error)[:50]}")
                        continue
        except Exception as pdf_error:
            # Registrar falha se não conseguir abrir o PDF
            resultado["erro"] = f"Erro ao abrir PDF: {str(pdf_error)[:50]}"
            return resultado

        full_raw_text = "\n".join(all_text_pages)

        # Limpar cabeçalhos e rodapés, consolidar linhas em parágrafos
        merged = merge_lines(cleaned_lines)
        normalized_paragraphs = normalize_paragraphs(merged)
        texto_completo_limpo = "\n\n".join(normalized_paragraphs).strip()

        # -------------------------------------------------
        # 3. Extração de número do processo
        # -------------------------------------------------
        numero_processo = extrair_numero_processo(full_raw_text, caminho_pdf.name)

        resultado["numeroProcesso"] = numero_processo
        resultado["texto_completo_limpo"] = texto_completo_limpo
        resultado["sucesso"] = True
        
        return resultado

    except Exception as e:
        resultado["erro"] = f"Erro ao processar PDF: {str(e)}"
        logger.error(f"Erro ao processar {caminho_pdf}: {str(e)}")
        return resultado


def processar_pasta_decisoes(
    pasta_decisoes: str,
    arquivo_csv_saida: str = None,
) -> Dict:
    """
    Processa todos os PDFs em uma pasta e salva os textos extraídos em CSV.
    
    Args:
        pasta_decisoes: Caminho da pasta com PDFs
        arquivo_csv_saida: Caminho do arquivo CSV de saída (default: pasta_decisoes/decisoes_extraidas.csv)
    
    Returns:
        Dicionário com estatísticas do processamento
    """
    pasta_decisoes = Path(pasta_decisoes)
    
    # Definir arquivo de saída padrão
    if arquivo_csv_saida is None:
        arquivo_csv_saida = pasta_decisoes / "decisoes_extraidas.csv"
    else:
        arquivo_csv_saida = Path(arquivo_csv_saida)
    
    # Encontrar todos os PDFs
    arquivos_pdf = list(pasta_decisoes.glob("*.pdf"))
    logger.info(f"Encontrados {len(arquivos_pdf)} arquivos PDF")
    
    # Processar cada PDF
    resultados = []
    erros = []
    
    for idx, arquivo_pdf in enumerate(arquivos_pdf, 1):
        logger.info(f"[{idx}/{len(arquivos_pdf)}] Processando {arquivo_pdf.name}...")
        
        info = extrair_info_pdf(str(arquivo_pdf))
        
        if info["sucesso"]:
            resultados.append(info)
            logger.info(f"Texto extraído com sucesso")
        else:
            logger.warning(f"Erro ao processar: {info['erro']}")
            erros.append({
                "arquivo": arquivo_pdf.name,
                "erro": info["erro"]
            })
    
    # Salvar CSV consolidado
    try:
        df = pd.DataFrame(resultados)
        
        # Reordenar colunas para facilitar análise
        df = df[["arquivo", "numeroProcesso", "texto_completo_limpo"]]
        
        # Renomear colunas para maior clareza
        df = df.rename(columns={"numeroProcesso": "numero_processo", "texto_completo_limpo": "decisao_completa"})
        
        # Usar ponto-e-vírgula como delimitador por compatibilidade com conteúdo
        df.to_csv(arquivo_csv_saida, index=False, encoding="utf-8", sep=";", quoting=1)
        
        logger.info(f"Arquivo salvo com sucesso: {arquivo_csv_saida}")
        logger.info(f"Total de registros processados: {len(df)}")
        
    except Exception as e:
        logger.error(f"Erro ao salvar arquivo CSV: {str(e)}")
    
    return {
        "total_arquivos": len(arquivos_pdf),
        "processados_com_sucesso": len(resultados),
        "com_erro": len(erros),
        "arquivo_csv": str(arquivo_csv_saida),
        "pasta_txt": "(nao utilizado)",
        "pasta_json": "(nao utilizado)",
        "json_consolidado": "(nao utilizado)",
    }


if __name__ == "__main__":
    # Definir pasta de origem com PDFs
    pasta = "data/notebook1/decisoes"
    
    logger.info("Iniciando extração de decisões TJCE...")
    stats = processar_pasta_decisoes(pasta)
    
    print("\n" + "=" * 80)
    print("RESUMO DO PROCESSAMENTO")
    print("=" * 80)
    print(f"Total de arquivos: {stats['total_arquivos']}")
    print(f"Processados com sucesso: {stats['processados_com_sucesso']}")
    print(f"Com erro: {stats['com_erro']}")
    print(f"\nArquivo consolidado:")
    print(f"  - CSV: {stats['arquivo_csv']}")
    print("=" * 80)
