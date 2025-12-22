"""
Módulos do Pipeline de Coleta de Dados para ML
===============================================

Este pacote contém três módulos principais:

1. scraper_tjce: Web scraping de dados do TJCE
2. inferir_sexo: Inferência de sexo a partir de nomes
3. gerar_features: Geração de features para ML

Cada módulo pode ser executado independentemente ou através do
orquestrador principal (coletar_dados_ml.py).
"""

__version__ = "1.0.0"
__all__ = ["scraper_tjce", "inferir_sexo", "gerar_features"]
