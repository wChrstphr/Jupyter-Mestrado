import pandas as pd
import os
import sys

# Forçar UTF-8 no console Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Configurações
ARQUIVO_PROCESSOS = "data/csv/dados_processos_tjce.csv"
ARQUIVO_NOMES = "data/nomes/nomes.csv.gz"
ARQUIVO_SAIDA = "data/csv/dados_processos_com_sexo.csv"


def carregar_banco_nomes(arquivo_nomes):
    """
    Carrega o banco de dados de nomes brasileiros.
    Ajuste as colunas conforme a estrutura do seu arquivo.
    """
    df_nomes = pd.read_csv(
        arquivo_nomes,
        compression="gzip",
        encoding="utf-8",
    )

    print("\n1. Verificando headers do csv de nomes brasileiros:")
    print(df_nomes.columns)

    return df_nomes


def extrair_primeiro_nome(nome_completo):
    """
    Extrai o primeiro nome de um nome completo.
    """
    if pd.isna(nome_completo) or nome_completo == "":
        return None

    # Remove espaços extras e pega o primeiro nome
    primeiro_nome = str(nome_completo).strip().split()[0]
    return primeiro_nome.upper()  # Normaliza para maiúsculas


def buscar_sexo(primeiro_nome, df_nomes, coluna_nome="nome", coluna_sexo="sexo"):
    """
    Busca o sexo no banco de dados de nomes.

    Args:
        primeiro_nome: Primeiro nome a buscar
        df_nomes: DataFrame com banco de nomes
        coluna_nome: Nome da coluna que contém os nomes
        coluna_sexo: Nome da coluna que contém o sexo

    Returns:
        'M', 'F' ou 'Indefinido'
    """
    if primeiro_nome is None:
        return "Indefinido"

    # Busca o nome no banco
    resultado = df_nomes[df_nomes[coluna_nome].str.upper() == primeiro_nome]

    if len(resultado) == 0:
        return "Indefinido"
    elif len(resultado) == 1:
        return resultado.iloc[0][coluna_sexo]


def inferir_sexo_processos(
    arquivo_processos, df_nomes, coluna_nome="nome", coluna_sexo="sexo"
):
    """
    Infere o sexo do juiz e requerente nos processos.
    """
    df_processos = pd.read_csv(arquivo_processos, encoding="utf-8")
    # Extrai primeiro nome e infere sexo
    df_processos["primeiro_nome_juiz"] = df_processos["juiz"].apply(
        extrair_primeiro_nome
    )
    df_processos["primeiro_nome_requerente"] = df_processos["requerente"].apply(
        extrair_primeiro_nome
    )
    # print primeiros registros de df_processos
    print("\n2. Extraindo primeiros nomes das partes:\n   Primeiros registros de df_processos após extração de primeiros nomes:")
    print(df_processos.head())

    print("\n3. Inferindo sexo dos juízes e requerentes...")
    df_processos["sexo_juiz"] = df_processos["primeiro_nome_juiz"].apply(
        lambda x: buscar_sexo(x, df_nomes, coluna_nome, coluna_sexo)
    )

    df_processos["sexo_requerente"] = df_processos["primeiro_nome_requerente"].apply(
        lambda x: buscar_sexo(x, df_nomes, coluna_nome, coluna_sexo)
    )

    # Remove colunas temporárias de primeiro nome
    df_processos = df_processos.drop(
        columns=["primeiro_nome_juiz", "primeiro_nome_requerente"]
    )

    return df_processos


def executar_inferencia_sexo():
    """
    Função principal: infere sexo de juízes e requerentes
    """
    # Verifica se os arquivos existem
    print("\n" + "=" * 60)
    print("INFERÊNCIA DE SEXO NOS PROCESSOS")
    print("=" * 60)

    if not os.path.exists(ARQUIVO_PROCESSOS):
        print(f"Erro: Arquivo {ARQUIVO_PROCESSOS} não encontrado!")
        return

    if not os.path.exists(ARQUIVO_NOMES):
        print(f"Erro: Arquivo {ARQUIVO_NOMES} não encontrado!")
        return

    # Carrega banco de nomes
    df_nomes = carregar_banco_nomes(ARQUIVO_NOMES)

    # IMPORTANTE: Ajuste os nomes das colunas conforme seu arquivo
    # Exemplos comuns: 'nome', 'first_name', 'name'
    # Exemplos comuns: 'sexo', 'gender', 'sex'
    coluna_nome = "first_name"
    coluna_sexo = "classification"

    # Infere sexo nos processos
    df_resultado = inferir_sexo_processos(
        ARQUIVO_PROCESSOS, df_nomes, coluna_nome, coluna_sexo
    )

    # Salva resultado
    df_resultado.to_csv(ARQUIVO_SAIDA, index=False, encoding="utf-8")
    print(f"\n4. Salvando resultados em {ARQUIVO_SAIDA}")

    # Estatísticas
    print(f"\n{'-'*30}")
    print(f"ESTATÍSTICAS")
    print(f"{'-'*30}")

    print(f"\nSexo dos Juízes:")
    print(df_resultado["sexo_juiz"].value_counts())

    print(f"\nSexo dos Requerentes:")
    print(df_resultado["sexo_requerente"].value_counts())

    # Amostra do resultado
    print(f"\n{'-'*30}")
    print(f"AMOSTRA")
    print(f"{'-'*30}")
    print(df_resultado[["juiz", "sexo_juiz", "requerente", "sexo_requerente"]].head(10))


if __name__ == "__main__":
    executar_inferencia_sexo()
