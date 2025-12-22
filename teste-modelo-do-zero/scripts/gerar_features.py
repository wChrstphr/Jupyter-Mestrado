"""
Script para gerar features do dados_completos.json e integrá-las com dados_processos_com_sexo.csv
Gera dataset limpo e otimizado para modelo de Machine Learning:
- Remove features desnecessárias
- Cria features derivadas (eh_segunda, eh_sexta)
- Transforma assuntos em features binárias
- Converte sexo para binário (0=M, 1=F, -1=Indefinido)
- Filtra apenas registros com status 'sucesso'
- Substitui numero_processo por ID genérico
"""

import json
import pandas as pd
from datetime import datetime
import unicodedata


def extrair_features_temporais(data_ajuizamento_str, data_atualizacao_str):
    """Extrai features temporais das datas"""
    try:
        # Converter dataAjuizamento (formato: 20250930000000)
        data_ajuiz = datetime.strptime(data_ajuizamento_str, "%Y%m%d%H%M%S")

        # Converter dataHoraUltimaAtualizacao (formato ISO) - remover timezone para evitar erro
        data_atual_str = data_atualizacao_str.replace("Z", "").split(".")[0]
        data_atual = datetime.fromisoformat(data_atual_str)

        # Calcular diferença
        dias_desde_ajuizamento = (data_atual - data_ajuiz).days
        dia_semana = data_ajuiz.weekday()

        return {
            "dias_desde_ajuizamento": dias_desde_ajuizamento,
            "ano_ajuizamento": data_ajuiz.year,
            "mes_ajuizamento": data_ajuiz.month,
            "eh_segunda": 1 if dia_semana == 0 else 0,
            "eh_sexta": 1 if dia_semana == 4 else 0,
        }
    except Exception as e:
        print(f"Erro ao processar datas: {e}")
        return {
            "dias_desde_ajuizamento": 0,
            "ano_ajuizamento": 0,
            "mes_ajuizamento": 0,
            "eh_segunda": 0,
            "eh_sexta": 0,
        }


def extrair_features_assuntos(assuntos):
    """Extrai features relacionadas aos assuntos do processo"""
    assuntos_text = " ".join([a.get("nome", "").lower() for a in assuntos])
    assunto_principal = (
        assuntos[0].get("nome", "Desconhecido") if assuntos else "Desconhecido"
    )

    return {
        "qtd_assuntos": len(assuntos),
        "tem_tutela_urgencia": (
            1 if ("tutela" in assuntos_text and "urgencia" in assuntos_text) else 0
        ),
        "tem_obrigacao_fazer": 1 if "obrigação de fazer" in assuntos_text else 0,
        "tem_dano_moral": 1 if "dano moral" in assuntos_text else 0,
        "assunto_principal": assunto_principal,
    }


def extrair_horario_decisao(movimentos):
    """
    Verifica se a decisão (Procedência/Improcedência) foi no horário de almoço (11h-13h)

    Returns:
        dict: {
            'eh_horario_almoco': int (1 se entre 11h-13h, 0 caso contrário)
        }
    """
    for mov in movimentos:
        nome_mov = mov.get("nome", "")

        # Verificar se é uma decisão
        if "Procedência" in nome_mov or "Improcedência" in nome_mov:
            data_hora = mov.get("dataHora", "")

            if data_hora:
                try:
                    # Formato ISO: "2025-09-25T11:03:41.000Z"
                    dt = datetime.fromisoformat(data_hora.replace("Z", "+00:00"))
                    hora = dt.hour

                    # Verificar se é horário de almoço (11h-13h inclusive)
                    eh_horario_almoco = 1 if (11 <= hora <= 13) else 0

                    return {
                        "eh_horario_almoco": eh_horario_almoco,
                    }
                except Exception as e:
                    print(f"Erro ao processar dataHora: {e}")

    # Se não encontrou decisão ou não tem dataHora, retornar valores padrão
    return {
        "eh_horario_almoco": 0,
    }


def extrair_features_movimentos(movimentos, dias_desde_ajuizamento):
    """Extrai features relacionadas aos movimentos do processo"""
    qtd_movimentos = len(movimentos)

    # Calcular velocidade (evitar divisão por zero)
    velocidade = (
        qtd_movimentos / dias_desde_ajuizamento if dias_desde_ajuizamento > 0 else 0
    )

    return {
        "qtd_movimentos": qtd_movimentos,
        "velocidade_movimentos": round(velocidade, 4),
    }


def processar_processo(processo_source):
    """Processa um processo e extrai apenas as features necessárias"""

    # Dados básicos
    numero_processo = processo_source.get("numeroProcesso", "")

    # Features temporais
    features_temporais = extrair_features_temporais(
        processo_source.get("dataAjuizamento", ""),
        processo_source.get("dataHoraUltimaAtualizacao", ""),
    )

    # Órgão julgador
    orgao_julgador = processo_source.get("orgaoJulgador", {})
    nome_orgao = orgao_julgador.get("nome", "")
    municipio_fortaleza = 1 if "FORTALEZA" in nome_orgao.upper() else 0

    # Features de assuntos
    assuntos = processo_source.get("assuntos", [])
    features_assuntos = extrair_features_assuntos(assuntos)

    # Features de movimentos
    movimentos = processo_source.get("movimentos", [])
    features_movimentos = extrair_features_movimentos(
        movimentos, features_temporais["dias_desde_ajuizamento"]
    )

    # Features de horário da decisão
    features_horario_decisao = extrair_horario_decisao(movimentos)

    # Complexidade
    complexidade_score = (
        features_assuntos["qtd_assuntos"] * features_movimentos["qtd_movimentos"]
    )

    # Verificar se tem recurso
    classe_info = processo_source.get("classe", {})
    classe_nome = classe_info.get("nome", "Desconhecido")
    tem_recurso = (
        1
        if any(
            palavra in classe_nome.lower()
            for palavra in ["agravo", "apelação", "recurso"]
        )
        else 0
    )

    # Montar dicionário com apenas as features necessárias
    features = {
        "numero_processo": numero_processo,
        **features_temporais,
        "municipio_fortaleza": municipio_fortaleza,
        **features_assuntos,
        **features_movimentos,
        **features_horario_decisao,  # Adiciona eh_horario_almoco
        "complexidade_score": complexidade_score,
        "tem_recurso": tem_recurso,
    }

    return features


def executar_geracao_features():
    """
    Função principal: gera features para modelo ML
    """
    print("=" * 80)
    print("GERAÇÃO DE FEATURES PARA MODELO ML")
    print("=" * 80)

    # 1. Carregar dados_completos.json
    print("\n[1/4] Carregando dados_completos.json...")
    with open("data/output/dados_completos.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    processos = data["hits"]["hits"]
    print(f"   OK {len(processos)} processos carregados")

    # 2. Extrair features de cada processo
    print("\n[2/4] Extraindo features...")
    features_list = []

    for i, processo in enumerate(processos):
        if (i + 1) % 1000 == 0:
            print(f"   Processando: {i+1}/{len(processos)}")

        processo_source = processo["_source"]
        features = processar_processo(processo_source)
        features_list.append(features)

    df_features = pd.DataFrame(features_list)
    print(f"   OK {len(df_features)} processos com features extraídas")
    print(f"   OK {len(df_features.columns)} colunas geradas")

    # 3. Carregar dados_processos_com_sexo.csv e fazer merge
    print("\n[3/5] Integrando com dados_processos_com_sexo.csv...")
    try:
        df_sexo = pd.read_csv("data/output/dados_processos_com_sexo.csv")
        print(f"   OK {len(df_sexo)} processos com dados de sexo carregados")

        # Converter numero_processo para string com zeros à esquerda (20 dígitos)
        df_sexo["numero_processo"] = (
            df_sexo["numero_processo"].astype(str).str.zfill(20)
        )
        df_features["numero_processo"] = df_features["numero_processo"].astype(str)

        # Fazer merge pelo numero_processo
        df_final = df_features.merge(
            df_sexo[
                [
                    "numero_processo",
                    "sexo_juiz",
                    "sexo_requerente",
                    "sentenca_favoravel",
                    "status",
                    "texto_decisao",  # Adicionar texto da decisão
                ]
            ],
            on="numero_processo",
            how="inner",
        )

        print(f"   OK Merge realizado: {len(df_final)} processos no dataset final")

    except FileNotFoundError:
        print("   AVISO: Arquivo dados_processos_com_sexo.csv não encontrado")
        print("   -> Continuando apenas com features extraídas...")
        df_final = df_features

    # 4. Filtrar apenas registros com status 'sucesso' e transformar dados
    print("\n[4/5] Limpando e transformando dados...")
    registros_antes = len(df_final)
    df_final = df_final[df_final["status"] == "sucesso"].copy()
    print(f"   OK Filtrados {len(df_final)} registros com status 'sucesso'")
    print(f"   OK Removidos {registros_antes - len(df_final)} registros")

    # Transformar sexo em binário (0=M, 1=F, -1=Indefinido)
    df_final["sexo_juiz_bin"] = (
        df_final["sexo_juiz"]
        .map({"M": 0, "F": 1, "Indefinido": -1})
        .fillna(-1)
        .astype(int)
    )
    df_final["sexo_requerente_bin"] = (
        df_final["sexo_requerente"]
        .map({"M": 0, "F": 1, "Indefinido": -1})
        .fillna(-1)
        .astype(int)
    )
    print("   OK Sexo convertido (0=M, 1=F, -1=Indefinido)")

    # Transformar sentenca_favoravel em binário
    df_final["sentenca_favoravel"] = (
        df_final["sentenca_favoravel"]
        .map({True: 1, False: 0, "True": 1, "False": 0, 1: 1, 0: 0})
        .fillna(0)
        .astype(int)
    )
    print("   OK Sentença convertida (0=Improcedente, 1=Procedente)")

    # Criar features binárias para cada assunto principal
    assuntos_unicos = df_final["assunto_principal"].unique()
    print(f"   OK Criando {len(assuntos_unicos)} features de assunto...")

    for assunto in assuntos_unicos:
        # Limpar nome do assunto - remove acentos e caracteres especiais
        nome_limpo = assunto.lower()
        # Normalizar unicode removendo todos os acentos
        nome_limpo = unicodedata.normalize("NFD", nome_limpo)
        nome_limpo = nome_limpo.encode("ascii", "ignore").decode("utf-8")
        # Substituir caracteres especiais por underscore
        nome_limpo = (
            nome_limpo.replace(" ", "_")
            .replace("/", "_")
            .replace("(", "")
            .replace(")", "")
            .replace("-", "_")
        )
        nome_limpo = nome_limpo.replace("__", "_").strip("_")
        nome_feature = f"eh_{nome_limpo}"[:60]

        df_final[nome_feature] = (df_final["assunto_principal"] == assunto).astype(int)

    # Remover colunas desnecessárias
    colunas_remover = [
        "numero_processo",
        "sexo_juiz",
        "sexo_requerente",
        "status",
        "assunto_principal",
    ]
    df_final = df_final.drop(columns=colunas_remover)

    # Criar ID genérico
    df_final.insert(0, "id", range(1, len(df_final) + 1))

    print(f"   OK Dataset final com {len(df_final.columns)} features")

    # 5. Salvar dataset final
    print("\n[5/5] Salvando dataset_ml_limpo.csv...")
    output_file = "data/output/dataset_ml_limpo.csv"
    df_final.to_csv(output_file, index=False, encoding="utf-8")
    print(f"   OK Dataset salvo: {output_file}")

    # Estatísticas finais
    print("\n" + "=" * 80)
    print("RESUMO DO DATASET FINAL")
    print("=" * 80)
    print(f"\nTotal de processos: {len(df_final)}")
    print(f"Total de features: {len(df_final.columns)}")

    print("\nFEATURES FINAIS:")
    for i, col in enumerate(df_final.columns, 1):
        print(f"  {i:2d}. {col}")

    print("\nDISTRIBUICOES:")
    print("\nSexo dos Juizes:")
    print(f"  - Masculino (0): {(df_final['sexo_juiz_bin'] == 0).sum()}")
    print(f"  - Feminino (1): {(df_final['sexo_juiz_bin'] == 1).sum()}")
    print(f"  - Indefinido (-1): {(df_final['sexo_juiz_bin'] == -1).sum()}")

    print(f"\nSexo dos Requerentes:")
    print(f"  - Masculino (0): {(df_final['sexo_requerente_bin'] == 0).sum()}")
    print(f"  - Feminino (1): {(df_final['sexo_requerente_bin'] == 1).sum()}")
    print(f"  - Indefinido (-1): {(df_final['sexo_requerente_bin'] == -1).sum()}")

    print(f"\nSentenças:")
    print(f"  - Improcedente (0): {(df_final['sentenca_favoravel'] == 0).sum()}")
    print(f"  - Procedente (1): {(df_final['sentenca_favoravel'] == 1).sum()}")

    print("\nPREVIEW (5 primeiras linhas):")
    print(df_final.head())

    # Verificar valores faltantes
    print("\nValores faltantes:")
    missing = df_final.isnull().sum()
    if missing.sum() > 0:
        print(missing[missing > 0])
    else:
        print("   OK Nenhum valor faltante!")

    print("\n" + "=" * 80)
    print("PROCESSO CONCLUIDO!")
    print("=" * 80)


if __name__ == "__main__":
    executar_geracao_features()
