from scripts import scraper_tjce, inferir_sexo, gerar_features

import asyncio
import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))


def verificar_arquivo(caminho):
    return os.path.exists(caminho)


async def executar_scraping():
    print("\n[1/3] Web Scraping TJCE")

    if not verificar_arquivo("data/output/numeros_processos.csv"):
        print("Erro: data/output/numeros_processos.csv não encontrado")
        return False

    await scraper_tjce.executar_pipeline_scraping()
    return verificar_arquivo("data/output/dados_processos_tjce.csv")


def executar_inferencia_sexo():
    print("\n[2/3] Inferência de Sexo")

    if not verificar_arquivo("data/output/dados_processos_tjce.csv"):
        print("Erro: Execute o scraping primeiro")
        return False

    if not verificar_arquivo("data/input/nomes.csv.gz"):
        print("Erro: data/input/nomes.csv.gz não encontrado")
        return False

    inferir_sexo.executar_inferencia_sexo()
    return verificar_arquivo("data/output/dados_processos_com_sexo.csv")


def executar_features():
    print("\n[3/3] Geração de Features")

    if not verificar_arquivo("data/output/dados_completos.json"):
        print("Erro: data/output/dados_completos.json não encontrado")
        return False

    if not verificar_arquivo("data/output/dados_processos_com_sexo.csv"):
        print("Erro: Execute a inferência de sexo primeiro")
        return False

    gerar_features.executar_geracao_features()
    return verificar_arquivo("data/output/dataset_ml_limpo.csv")


async def executar_pipeline_completo():
    print("\nPipeline Completo: 3 etapas")

    if not await executar_scraping():
        print("Erro no scraping")
        return False

    if not executar_inferencia_sexo():
        print("Erro na inferência")
        return False

    if not executar_features():
        print("Erro na geração de features")
        return False

    print("\nPipeline concluído")
    print("Dataset final: data/output/dataset_ml_limpo.csv")
    return True


async def main():
    parser = argparse.ArgumentParser(description="Pipeline de coleta de dados para ML")
    parser.add_argument(
        "--etapa",
        choices=["scraping", "inferir_sexo", "features", "todas"],
        default="todas",
        help="Etapa a executar (padrão: todas)",
    )

    args = parser.parse_args()

    try:
        if args.etapa == "scraping":
            await executar_scraping()
        elif args.etapa == "inferir_sexo":
            executar_inferencia_sexo()
        elif args.etapa == "features":
            executar_features()
        else:
            await executar_pipeline_completo()
    except KeyboardInterrupt:
        print("\nCancelado")
        return
    except Exception as e:
        print(f"\nErro: {e}")
        return


if __name__ == "__main__":
    asyncio.run(main())
