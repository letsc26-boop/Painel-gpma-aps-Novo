import base64
import glob
import os
import numpy as np
import pandas as pd

# =========================================================
# 1. DEFINIR CAMINHOS E DIRETÓRIO PARA DIABÉTICOS
# =========================================================
pasta_trabalho = r"W:\GPMA\NCAIS\Residência\Letícia Stefany Costa\Relatorio indicadores de saúde\diabéticos\arquivos csv"
caminho_saida = r"W:\GPMA\NCAIS\Residência\Letícia Stefany Costa\Relatorio indicadores de saúde\diabéticos\Relatorio_PowerBI_Diabeticos.html"

if not os.path.exists(pasta_trabalho):
  os.makedirs(pasta_trabalho, exist_ok=True)

arquivos_csv = glob.glob(os.path.join(pasta_trabalho, "*.csv"))

if not arquivos_csv:
  print(f"Erro: Nenhum ficheiro CSV encontrado em: {pasta_trabalho}")
  exit()

print(f"=== A LER E UNIFICAR OS {len(arquivos_csv)} FICHEIROS DE DIABÉTICOS ===")


def limpar_e_converter_data(serie):
  if serie is None:
    return pd.Series([pd.NaT])
  s = (
      serie.astype(str)
      .str.replace('"', "")
      .str.replace("ï»¿", "")
      .str.strip()
  )
  s = s.replace(["-", "nan", "NaT", "None", "", "0"], np.nan)
  dt = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
  mask_iso = dt.isna() & s.notna()
  if mask_iso.any():
    dt.loc[mask_iso] = pd.to_datetime(
        s[mask_iso], format="%Y-%m-%d", errors="coerce"
    )
  return dt


lista_dfs = []
for arquivo in arquivos_csv:
  nome_arq = os.path.basename(arquivo)
  if "Relatorio" in nome_arq or "HTML" in nome_arq:
    continue

  try:
    temp_df = pd.read_csv(
        arquivo, sep=";", encoding="iso-8859-1", low_memory=False
    )
    temp_df.columns = (
        temp_df.columns.str.replace("ï»¿", "").str.replace('"', "").str.strip()
    )
    temp_df = temp_df.loc[
        :, ~temp_df.columns.str.contains(r"^Unnamed|\.\.\.", na=False)
    ]

    for c in temp_df.columns:
      c_lower = c.lower()
      if "peso e altura" in c_lower or (
          "peso" in c_lower and "altura" in c_lower and "data" in c_lower
      ):
        temp_df = temp_df.rename(
            columns={c: "Data da última medição de peso"}
        )

    if (
        "Data da última medição de altura" not in temp_df.columns
        and "Data da última medição de peso" in temp_df.columns
    ):
      temp_df["Data da última medição de altura"] = temp_df[
          "Data da última medição de peso"
      ]

    if not temp_df.empty:
      lista_dfs.append(temp_df)
      print(f"  -> [OK] Lido: {nome_arq} | Linhas: {len(temp_df)}")
  except Exception as e:
    print(f"  -> [ERRO] Falha ao ler {nome_arq}: {e}")

if not lista_dfs:
  print("Erro crítico: Nenhum dado válido foi carregado.")
  exit()

df = pd.concat(lista_dfs, ignore_index=True)
df = df.loc[:, ~df.columns.duplicated()]

data_atual = pd.to_datetime("today")
df["Data_Atual"] = data_atual

# 2. Conversão segura de colunas de data
colunas_data_para_converter = [
    "DATA",
    "Data da última consulta",
    "Data da avaliação dos pés",
    "Data da última avaliação de hemoglobina glicada",
    "Data da última solicitação de hemoglobina glicada",
    "Data da última medição de pressão arterial",
    "Data da última medição de peso",
    "Data da última medição de altura",
    "Datas_1ªVisitaDomiciliar",
    "Datas_2ªVisitaDomiciliar",
]

for col in colunas_data_para_converter:
  col_match = next((c for c in df.columns if col.lower() in c.lower()), None)
  if col_match:
    df[col] = limpar_e_converter_data(df[col_match])
    if col_match != col and col not in df.columns:
      df = df.rename(columns={col_match: col})
  else:
    df[col] = pd.NaT

# 3. REGRAS DE PONTUAÇÃO (Valores: 0 = Não atendido/Fora do prazo, 1 = Atendido)
dias_pes = (data_atual - df["Data da avaliação dos pés"]).dt.days
df["Pontuação_Pés"] = np.select(
    [df["Data da avaliação dos pés"].isna(), dias_pes <= 365],
    [0, 1],
    default=0,
)

df["Pontuação_Consultas"] = np.where(
    df["Data da última consulta"].notna()
    & ((data_atual - df["Data da última consulta"]).dt.days <= 180),
    1,
    0,
)

dias_pa = (
    data_atual - df["Data da última medição de pressão arterial"]
).dt.days
df["Pontuação_PA"] = np.select(
    [
        df["Data da última medição de pressão arterial"].isna(),
        dias_pa <= 180,
    ],
    [0, 1],
    default=0,
)

dias_hemo_av = (
    data_atual - df["Data da última avaliação de hemoglobina glicada"]
).dt.days
dias_hemo_sol = (
    data_atual - df["Data da última solicitação de hemoglobina glicada"]
).dt.days
cond_hemo = (dias_hemo_av <= 365) | (dias_hemo_sol <= 365)
df["Pontuação_Hemoglobina"] = np.select(
    [
        df["Data da última avaliação de hemoglobina glicada"].isna()
        & df["Data da última solicitação de hemoglobina glicada"].isna(),
        cond_hemo,
    ],
    [0, 1],
    default=0,
)

dias_entre_visitas = (
    df["Datas_2ªVisitaDomiciliar"] - df["Datas_1ªVisitaDomiciliar"]
).dt.days
dias_ate_segunda = (data_atual - df["Datas_2ªVisitaDomiciliar"]).dt.days
cond_v1 = (
    df["Datas_1ªVisitaDomiciliar"].notna()
    & df["Datas_2ªVisitaDomiciliar"].notna()
    & (dias_entre_visitas >= 30)
    & (dias_entre_visitas <= 365)
    & (dias_ate_segunda <= 365)
)
df["Pontuação_Visitas"] = np.where(cond_v1, 1, 0)

col_peso_val = next(
    (
        c
        for c in df.columns
        if "peso" in c.lower()
        and "última" in c.lower()
        and "data" not in c.lower()
    ),
    None,
)
col_alt_val = next(
    (
        c
        for c in df.columns
        if "altura" in c.lower()
        and "última" in c.lower()
        and "data" not in c.lower()
    ),
    None,
)
has_peso = (
    df[col_peso_val].notna()
    & (df[col_peso_val].astype(str).str.strip() != "-")
    & (df[col_peso_val].astype(str).str.strip() != "0")
    if col_peso_val
    else pd.Series([False] * len(df))
)
has_alt = (
    df[col_alt_val].notna()
    & (df[col_alt_val].astype(str).str.strip() != "-")
    & (df[col_alt_val].astype(str).str.strip() != "0")
    if col_alt_val
    else pd.Series([False] * len(df))
)
dias_peso = (data_atual - df["Data da última medição de peso"]).dt.days
cond_peso_alt = (
    has_peso
    & has_alt
    & df["Data da última medição de peso"].notna()
    & (dias_peso <= 365)
)
df["Pontuação_PesoAltura"] = np.where(cond_peso_alt, 1, 0)

# 4. Preparação dos dados para o JavaScript
df["DATA_STR"] = df["DATA"].dt.strftime("%Y-%m-%d")
df["UBS"] = (
    df["UBS"].fillna("Não informada") if "UBS" in df.columns else "Não informada"
)
df["EQUIPE"] = (
    df["EQUIPE"].fillna("Não informada")
    if "EQUIPE" in df.columns
    else "Não informada"
)

colunas_necessarias = [
    "DATA_STR",
    "UBS",
    "EQUIPE",
    "Pontuação_Consultas",
    "Pontuação_PA",
    "Pontuação_Pés",
    "Pontuação_Hemoglobina",
    "Pontuação_Visitas",
    "Pontuação_PesoAltura",
]

dados_json = df[colunas_necessarias].to_json(orient="records", force_ascii=False)

ubs_unicas = sorted(df["UBS"].unique().tolist())
datas_unicas = sorted(df["DATA_STR"].dropna().unique().tolist())

opcoes_ubs_html = "".join(
    [f'<option value="{u}">{u}</option>' for u in ubs_unicas]
)
opcoes_datas_html = "".join(
    [
        f'<option value="{d}">{d.split("-")[2]}/{d.split("-")[1]}/{d.split("-")[0]}</option>'
        for d in datas_unicas
    ]
)

# Carregar imagem GPMA local se existir
logo_src = ""
for img_nome in ["gpma.png", "gpma.jpg", "GPMA.png", "GPMA.jpg"]:
  caminho_img = os.path.join(pasta_trabalho, img_nome)
  if os.path.exists(caminho_img):
    with open(caminho_img, "rb") as img_file:
      encoded_img = base64.b64encode(img_file.read()).decode("utf-8")
      ext = img_nome.split(".")[-1].lower()
      mime = "image/jpeg" if ext in ["jpg", "jpeg"] else "image/png"
      logo_src = f"data:{mime};base64,{encoded_img}"
    break

logo_html = (
    f'<img src="{logo_src}" alt="GPMA Logo">'
    if logo_src
    else '<div style="font-weight:bold; color:#8B262B; font-size:12px;'
    ' text-align:center;">GPMA - APS</div>'
)

# Definição das abas de boas práticas para os Diabéticos
secoes_individuais = [
    (
        "pes",
        "AVALIAÇÃO DOS PÉS",
        (
            "Ter pelo menos 01 (uma) avaliação dos pés realizada nos últimos 12"
            " (doze) meses."
        ),
    ),
    (
        "vis",
        "VISITAS DOMICILIARES",
        (
            "Ter pelo menos 02 (duas) visitas domiciliares realizadas por"
            " ACS/TACS, com intervalo mínimo de 30 dias, nos últimos 12 meses."
        ),
    ),
    (
        "hem",
        "HEMOGLOBINA GLICADA",
        (
            "Ter pelo menos 01 (um) registro de solicitação de hemoglobina"
            " glicada realizada ou avaliada, nos últimos 12 (doze) meses."
        ),
    ),
    (
        "pa",
        "PRESSÃO ARTERIAL",
        (
            "Ter pelo menos 01 (um) registro de aferição de pressão arterial"
            " realizado nos últimos 06 (seis) meses."
        ),
    ),
    (
        "con",
        "CONSULTAS MÉDICA/ENF.",
        (
            "Ter pelo menos 01 (uma) consulta presencial ou remota realizada por"
            " médica(o) ou enfermeira(o), nos últimos 06 meses."
        ),
    ),
    (
        "peso",
        "PESO E ALTURA",
        (
            "Ter pelo menos 01 (um) registro simultâneo de peso e altura"
            " realizado nos últimos 12 (doze) meses."
        ),
    ),
]

html_secoes_abafas = ""
for c, titulo, sub in secoes_individuais:
  html_secoes_abafas += f"""
    <div id="view-{c}" class="page-view">
        <div class="header-container">
            <div>
                <div class="header-title">Monitoramento — Cuidado da Pessoa com Diabetes: {titulo}</div>
                <div class="header-subtitle"><b>BOA PRÁTICA:</b> {sub}</div>
            </div>
            <div class="top-buttons"><button class="btn-pb" onclick="mudarPagina('geral')">Voltar</button></div>
        </div>
        <div class="cards-container">
            <div class="card"><div class="card-title">Cumprimento</div><div id="{c}-val-cumprimento" class="card-value">0.00%</div></div>
            <div class="card"><div class="card-title">Não Atendido / Fora do Prazo</div><div id="{c}-val-naopreenchido" class="card-value">0.00%</div></div>
        </div>
        <div class="sub-grid">
            <div class="sub-col" style="flex: 1.2;">
                <div class="chart-box" style="max-height: 480px; display: flex; flex-direction: column;">
                    <div class="section-title">Evolução ao Longo do Tempo</div>
                    <div style="flex: 1; min-height: 200px; position: relative;"><canvas id="{c}-canvas-linhas"></canvas></div>
                    <div style="border-top: 2px solid #F3F2F1; padding-top: 8px; margin-top: 8px;">
                        <div class="filter-label" style="color: #8B262B; font-weight: bold;">Data de Referência</div>
                        <select id="{c}-filtro-data" class="filter-select" onchange="document.getElementById('filtro-data').value = this.value; filtrarDados();"><option value="TODAS">Todas as Datas</option>{opcoes_datas_html}</select>
                    </div>
                </div>
            </div>
            <div class="sub-col" style="flex: 1.8;">
                <div class="chart-box"><div class="section-title">Ranking por UBS</div><div id="{c}-ranking-ubs" style="display:flex; flex-direction:column; gap:6px;"></div></div>
                <div class="chart-box"><div class="section-title">Ranking por Equipe</div><div id="{c}-ranking-equipe" style="display:flex; flex-direction:column; gap:6px;"></div></div>
            </div>
        </div>
    </div>
    """

# 5. Geração do HTML Interativo Final para Diabéticos
html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Monitoramento - Diabéticos</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #EFEFEF; color: #323130; margin: 0; padding: 0; height: 100vh; overflow: hidden; }}
        .app-container {{ display: flex; height: 100vh; width: 100vw; }}
        
        .sidebar {{ width: 220px; background-color: #8B262B; color: white; display: flex; flex-direction: column; padding: 12px; box-shadow: 2px 0 5px rgba(0,0,0,0.1); z-index: 10; overflow-y: auto; flex-shrink: 0; }}
        
        /* Botão GPMA APS Centralizado e Estilizado */
        .sidebar-logo-container {{ display: flex; justify-content: center; width: 100%; margin-bottom: 15px; }}
        .sidebar-logo {{ background: white; border-radius: 8px; padding: 8px 12px; cursor: pointer; display: flex; justify-content: center; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.2); transition: transform 0.2s, box-shadow 0.2s; width: 90%; max-width: 170px; text-decoration: none; }}
        .sidebar-logo:hover {{ transform: scale(1.03); box-shadow: 0 4px 8px rgba(0,0,0,0.3); }}
        .sidebar-logo img {{ max-width: 100%; height: 40px; object-fit: contain; }}

        .sidebar-title {{ font-size: 13px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.2); padding-bottom: 5px; }}
        .filter-group {{ margin-bottom: 10px; }}
        .filter-label {{ font-size: 10px; text-transform: uppercase; font-weight: bold; margin-bottom: 3px; opacity: 0.9; }}
        .filter-select {{ width: 100%; padding: 5px; border-radius: 4px; border: none; font-size: 11px; background: white; color: #323130; }}
        
        .nav-section-title {{ font-size: 11px; font-weight: bold; text-transform: uppercase; margin: 10px 0 5px 0; border-bottom: 1px solid rgba(255,255,255,0.2); padding-bottom: 3px; }}
        .nav-menu {{ display: flex; flex-direction: column; gap: 6px; }}
        .nav-item {{ background-color: rgba(255,255,255,0.1); padding: 8px; border-radius: 4px; font-size: 10px; font-weight: bold; text-transform: uppercase; cursor: pointer; display: flex; align-items: center; gap: 8px; text-decoration: none; color: white; border: none; width: 100%; text-align: left; }}
        .nav-item:hover, .nav-item.active {{ background-color: white; color: #8B262B; }}
        .nav-item svg {{ width: 16px; height: 16px; fill: currentColor; flex-shrink: 0; }}
        
        .btn-limpar {{ margin-top: 10px; background-color: #A93238; color: white; border: 1px solid white; padding: 6px; border-radius: 4px; font-size: 11px; font-weight: bold; cursor: pointer; text-transform: uppercase; text-align: center; }}
        .btn-limpar:hover {{ background-color: white; color: #8B262B; }}

        .main-content {{ flex: 1; background-color: #F4F5F7; padding: 12px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }}
        
        .header-container {{ background-color: #8B262B; color: white; padding: 10px 15px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header-title {{ font-size: 15px; font-weight: bold; text-transform: uppercase; }}
        .header-subtitle {{ font-size: 10px; opacity: 0.9; margin-top: 2px; max-width: 600px; }}
        .top-buttons {{ display: flex; gap: 6px; }}
        .btn-pb {{ background-color: #A93238; color: white; border: 1px solid white; padding: 5px 10px; border-radius: 4px; font-size: 10px; font-weight: bold; cursor: pointer; text-transform: uppercase; }}
        .btn-pb:hover {{ background-color: white; color: #8B262B; }}

        .cards-container {{ display: flex; gap: 10px; }}
        .card {{ background: white; border-radius: 6px; padding: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1; text-align: center; border-top: 4px solid #8B262B; }}
        .card-title {{ font-size: 9px; color: #605E5C; text-transform: uppercase; font-weight: bold; }}
        .card-value {{ font-size: 18px; font-weight: bold; color: #8B262B; margin-top: 2px; }}

        .main-grid {{ display: flex; gap: 10px; flex: 1; }}
        .box-left {{ background: white; border-radius: 6px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1.2; display: flex; flex-direction: column; gap: 10px; }}
        .box-right {{ background: white; border-radius: 6px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1.8; overflow-y: auto; max-height: 440px; }}
        .section-title {{ font-size: 11px; color: #8B262B; font-weight: bold; text-transform: uppercase; margin-bottom: 8px; border-bottom: 2px solid #F3F2F1; padding-bottom: 4px; }}
        
        .metric-row {{ display: flex; align-items: center; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #F3F2F1; font-size: 11px; cursor: pointer; }}
        .metric-row:hover {{ background-color: #FAF9F8; }}
        .metric-left {{ display: flex; align-items: center; gap: 10px; max-width: 75%; }}
        .metric-icon {{ width: 22px; height: 22px; fill: #8B262B; flex-shrink: 0; }}
        .metric-label {{ color: #323130; line-height: 1.2; }}
        .metric-val {{ font-weight: bold; color: #8B262B; font-size: 13px; }}

        .page-view {{ display: none; flex-direction: column; gap: 10px; flex: 1; }}
        .page-view.active {{ display: flex; }}
        .sub-grid {{ display: flex; gap: 10px; flex: 1; }}
        .sub-col {{ display: flex; flex-direction: column; gap: 10px; flex: 1; }}
        .chart-box {{ background: white; border-radius: 6px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1; overflow-y: auto; max-height: 230px; }}
    </style>
</head>
<body>

    <div class="app-container">
        <!-- BARRA LATERAL -->
        <div class="sidebar">
            <div class="sidebar-logo-container">
                <a href="../Painel_GPMA_APS.html" class="sidebar-logo" title="Página Inicial GPMA">
                    {logo_html}
                </a>
            </div>

            <div class="sidebar-title">Filtros</div>
            <div class="filter-group">
                <div class="filter-label">UBS</div>
                <select id="filtro-ubs" class="filter-select" onchange="atualizarEquipes(); filtrarDados();">
                    <option value="TODAS">Todas as UBS</option>
                    {opcoes_ubs_html}
                </select>
            </div>
            <div class="filter-group">
                <div class="filter-label">Equipe</div>
                <select id="filtro-equipe" class="filter-select" onchange="filtrarDados();">
                    <option value="TODAS">Todas as Equipes</option>
                </select>
            </div>

            <div class="nav-section-title">Boas Práticas</div>
            <div class="nav-menu">
                <button id="nav-pes" class="nav-item" onclick="mudarPagina('pes')"><svg viewBox="0 0 24 24"><path d="M19 20H5V18H19V20M17.5 14C19 14 20 12.5 20 11C20 9.5 19 8 17.5 8C16 8 15 9.5 15 11C15 12.5 16 14 17.5 14M6.5 14C8 14 9 12.5 9 11C9 9.5 8 8 6.5 8C5 8 4 9.5 4 11C4 12.5 5 14 6.5 14M12 2C9.24 2 7 4.24 7 7C7 9.22 8.54 11.11 10.64 11.75L11 16H13L13.36 11.75C15.46 11.11 17 9.22 17 7C17 4.24 14.76 2 12 2Z"/></svg>Avaliação dos Pés</button>
                <button id="nav-vis" class="nav-item" onclick="mudarPagina('vis')"><svg viewBox="0 0 24 24"><path d="M12 3L2 12H5V20H10V14H14V20H19V12H22L12 3Z"/></svg>Visitas Domiciliares</button>
                <button id="nav-hem" class="nav-item" onclick="mudarPagina('hem')"><svg viewBox="0 0 24 24"><path d="M18 2H6C4.9 2 4 2.9 4 4V20C4 21.1 4.9 22 6 22H18C19.1 22 20 21.1 20 20V4C20 2.9 19.1 2 18 2M11 16H8V14H11V16M16 12H8V10H16V12M16 8H8V6H16V8Z"/></svg>Hemoglobina Glicada</button>
                <button id="nav-pa" class="nav-item" onclick="mudarPagina('pa')"><svg viewBox="0 0 24 24"><path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z"/></svg>Pressão Arterial</button>
                <button id="nav-con" class="nav-item" onclick="mudarPagina('con')"><svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12C2 17.52 6.48 22 12 22C17.52 22 22 17.52 22 12C22 6.48 17.52 2 12 2M10 17L5 12L6.41 10.59L10 14.17L17.59 6.58L19 8L10 17Z"/></svg>Consultas Médica/Enf.</button>
                <button id="nav-peso" class="nav-item" onclick="mudarPagina('peso')"><svg viewBox="0 0 24 24"><path d="M19 3H5C3.9 3 3 3.9 3 5V19C3 20.1 3.9 21 5 21H19C20.1 21 21 20.1 21 19V5C21 3.9 20.1 3 19 3M12 6C13.66 6 15 7.34 15 9C15 10.66 13.66 12 12 12C10.34 12 9 10.66 9 9C9 7.34 10.34 6 12 6M16 16H8V15C8 13.67 10.67 13 12 13C13.33 13 16 13.67 16 15V16Z"/></svg>Peso e Altura</button>
            </div>

            <div class="btn-limpar" onclick="limparFiltros()">Limpar Filtros</div>
        </div>

        <!-- CONTEÚDO PRINCIPAL -->
        <div class="main-content">

            <!-- PÁGINA 1: VISÃO GERAL -->
            <div id="view-geral" class="page-view active">
                <div class="header-container">
                    <div>
                        <div class="header-title">Monitoramento — Cuidado da Pessoa com Diabetes</div>
                        <div class="header-subtitle">Tem como objetivo avaliar o acesso e monitoramento efetivo do cuidado integral à saúde das pessoas com diabetes com incentivo à captação precoce.</div>
                    </div>
                </div>

                <div class="cards-container">
                    <div class="card">
                        <div class="card-title">Total de Diabéticos</div>
                        <div id="val-total" class="card-value">0</div>
                    </div>
                    <div class="card">
                        <div class="card-title">Média Boas Práticas</div>
                        <div id="val-media-praticas" class="card-value">0.00%</div>
                    </div>
                    <div class="card">
                        <div class="card-title">Total UBS</div>
                        <div id="val-ubs" class="card-value">0</div>
                    </div>
                    <div class="card">
                        <div class="card-title">Total Equipes</div>
                        <div id="val-equipes" class="card-value">0</div>
                    </div>
                </div>

                <div class="main-grid">
                    <div class="box-left">
                        <div class="section-title">Ranking Média de Cumprimento por UBS</div>
                        <div id="ranking-container" style="overflow-y: auto; max-height: 290px; flex: 1;"></div>
                        
                        <div style="border-top: 2px solid #F3F2F1; padding-top: 8px;">
                            <div class="filter-label" style="color: #8B262B; font-weight: bold;">Data de Referência</div>
                            <select id="filtro-data" class="filter-select" onchange="filtrarDados();" style="border: 1px solid #8B262B;">
                                <option value="TODAS">Todas as Datas</option>
                                {opcoes_datas_html}
                            </select>
                        </div>
                    </div>

                    <div class="box-right">
                        <div class="section-title">% de Não Cumprimento das Boas Práticas</div>
                        
                        <div class="metric-row" onclick="mudarPagina('pes')">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M19 20H5V18H19V20M17.5 14C19 14 20 12.5 20 11C20 9.5 19 8 17.5 8C16 8 15 9.5 15 11C15 12.5 16 14 17.5 14M6.5 14C8 14 9 12.5 9 11C9 9.5 8 8 6.5 8C5 8 4 9.5 4 11C4 12.5 5 14 6.5 14M12 2C9.24 2 7 4.24 7 7C7 9.22 8.54 11.11 10.64 11.75L11 16H13L13.36 11.75C15.46 11.11 17 9.22 17 7C17 4.24 14.76 2 12 2Z"/></svg>
                                <div class="metric-label">Ter pelo menos 01 (uma) avaliação dos pés realizada nos últimos 12 (doze) meses.</div>
                            </div>
                            <div id="nao-pes" class="metric-val">0.00%</div>
                        </div>

                        <div class="metric-row" onclick="mudarPagina('vis')">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M12 3L2 12H5V20H10V14H14V20H19V12H22L12 3Z"/></svg>
                                <div class="metric-label">Ter pelo menos 02 (duas) visitas domiciliares realizadas por ACS/TACS, com intervalo mínimo de 30 dias, nos últimos 12 meses.</div>
                            </div>
                            <div id="nao-vis" class="metric-val">0.00%</div>
                        </div>

                        <div class="metric-row" onclick="mudarPagina('hem')">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M18 2H6C4.9 2 4 2.9 4 4V20C4 21.1 4.9 22 6 22H18C19.1 22 20 21.1 20 20V4C20 2.9 19.1 2 18 2M11 16H8V14H11V16M16 12H8V10H16V12M16 8H8V6H16V8Z"/></svg>
                                <div class="metric-label">Ter pelo menos 01 (um) registro de solicitação de hemoglobina glicada realizada ou avaliada, nos últimos 12 (doze) meses.</div>
                            </div>
                            <div id="nao-hem" class="metric-val">0.00%</div>
                        </div>

                        <div class="metric-row" onclick="mudarPagina('pa')">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z"/></svg>
                                <div class="metric-label">Ter pelo menos 01 (um) registro de aferição de pressão arterial realizado nos últimos 06 (seis) meses.</div>
                            </div>
                            <div id="nao-pa" class="metric-val">0.00%</div>
                        </div>

                        <div class="metric-row" onclick="mudarPagina('con')">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12C2 17.52 6.48 22 12 22C17.52 22 22 17.52 22 12C22 6.48 17.52 2 12 2M10 17L5 12L6.41 10.59L10 14.17L17.59 6.58L19 8L10 17Z"/></svg>
                                <div class="metric-label">Ter pelo menos 01 (uma) consulta presencial ou remota realizada por médica(o) ou enfermeira(o), nos últimos 06 meses.</div>
                            </div>
                            <div id="nao-con" class="metric-val">0.00%</div>
                        </div>

                        <div class="metric-row" onclick="mudarPagina('peso')" style="border-bottom: none;">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M19 3H5C3.9 3 3 3.9 3 5V19C3 20.1 3.9 21 5 21H19C20.1 21 21 20.1 21 19V5C21 3.9 20.1 3 19 3M12 6C13.66 6 15 7.34 15 9C15 10.66 13.66 12 12 12C10.34 12 9 10.66 9 9C9 7.34 10.34 6 12 6M16 16H8V15C8 13.67 10.67 13 12 13C13.33 13 16 13.67 16 15V16Z"/></svg>
                                <div class="metric-label">Ter pelo menos 01 (um) registro simultâneo de peso e altura realizado nos últimos 12 (doze) meses.</div>
                            </div>
                            <div id="nao-peso" class="metric-val">0.00%</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- INSERÇÃO DAS ABAS INDIVIDUAIS -->
            {html_secoes_abafas}

        </div>
    </div>

    <script>
        const dadosOriginais = {dados_json};
        let dadosFiltrados = [...dadosOriginais];
        let activeView = 'geral';
        let charts = {{}};

        function mudarPagina(viewId) {{
            activeView = viewId;
            document.querySelectorAll('.page-view').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            
            document.getElementById('view-' + viewId).classList.add('active');
            const navBtn = document.getElementById('nav-' + viewId);
            if(navBtn) navBtn.classList.add('active');
            
            filtrarDados();
        }}

        function atualizarEquipes() {{
            const ubsSelecionada = document.getElementById('filtro-ubs').value;
            const selectEquipe = document.getElementById('filtro-equipe');
            selectEquipe.innerHTML = '<option value="TODAS">Todas as Equipes</option>';

            const equipes = [...new Set(dadosOriginais
                .filter(d => ubsSelecionada === 'TODAS' || d.UBS === ubsSelecionada)
                .map(d => d.EQUIPE))].sort();

            equipes.forEach(eq => {{
                const opt = document.createElement('option');
                opt.value = eq;
                opt.textContent = eq;
                selectEquipe.appendChild(opt);
            }});
        }}

        function limparFiltros() {{
            document.getElementById('filtro-ubs').value = 'TODAS';
            atualizarEquipes();
            document.getElementById('filtro-equipe').value = 'TODAS';
            document.getElementById('filtro-data').value = 'TODAS';
            
            ['pes', 'vis', 'hem', 'pa', 'con', 'peso'].forEach(k => {{
                const sel = document.getElementById(k + '-filtro-data');
                if(sel) sel.value = 'TODAS';
            }});

            filtrarDados();
        }}

        function filtrarDados() {{
            const ubs = document.getElementById('filtro-ubs').value;
            const equipe = document.getElementById('filtro-equipe').value;
            const dataRef = document.getElementById('filtro-data').value;

            if(activeView !== 'geral') {{
                const indSel = document.getElementById(activeView + '-filtro-data');
                if(indSel && indSel.value !== dataRef) {{
                    indSel.value = dataRef;
                }}
            }}

            dadosFiltrados = dadosOriginais.filter(d => {{
                return (ubs === 'TODAS' || d.UBS === ubs) &&
                       (equipe === 'TODAS' || d.EQUIPE === equipe) &&
                       (dataRef === 'TODAS' || d.DATA_STR === dataRef);
            }});

            atualizarDashboard();
        }}

        function atualizarDashboard() {{
            const total = dadosFiltrados.length;
            document.getElementById('val-total').textContent = total;
            
            const ubsSet = new Set(dadosFiltrados.map(d => d.UBS));
            const equipeSet = new Set(dadosFiltrados.map(d => d.EQUIPE));
            document.getElementById('val-ubs').textContent = ubsSet.size;
            document.getElementById('val-equipes').textContent = equipeSet.size;

            if (total === 0) {{
                document.getElementById('val-media-praticas').textContent = '0.00%';
                ['pes', 'vis', 'hem', 'pa', 'con', 'peso'].forEach(k => {{
                    const el = document.getElementById('nao-' + k);
                    if(el) el.textContent = '0.00%';
                }});
                gerarRankingUBS();
                return;
            }}

            const criterios = ['Pontuação_Pés', 'Pontuação_Visitas', 'Pontuação_Hemoglobina', 'Pontuação_PA', 'Pontuação_Consultas', 'Pontuação_PesoAltura'];
            let somaTotalPraticas = 0;

            criterios.forEach(col => {{
                const somaCol = dadosFiltrados.reduce((acc, d) => acc + d[col], 0);
                somaTotalPraticas += somaCol;
            }});

            const mediaGeral = (somaTotalPraticas / (total * criterios.length)) * 100;
            document.getElementById('val-media-praticas').textContent = mediaGeral.toFixed(2) + '%';

            const mapChaves = {{ 'pes': 'Pontuação_Pés', 'vis': 'Pontuação_Visitas', 'hem': 'Pontuação_Hemoglobina', 'pa': 'Pontuação_PA', 'con': 'Pontuação_Consultas', 'peso': 'Pontuação_PesoAltura' }};
            
            Object.keys(mapChaves).forEach(k => {{
                const col = mapChaves[k];
                const somaC = dadosFiltrados.reduce((acc, d) => acc + d[col], 0);
                const naoAtendidoPct = 100 - ((somaC / total) * 100);
                const el = document.getElementById('nao-' + k);
                if(el) el.textContent = naoAtendidoPct.toFixed(2) + '%';
            }});

            gerarRankingUBS();

            if (activeView !== 'geral') {{
                atualizarAbaIndividual(activeView, total);
            }}
        }}

        function atualizarAbaIndividual(criterio, total) {{
            const keyMap = {{ 'pes': 'Pontuação_Pés', 'vis': 'Pontuação_Visitas', 'hem': 'Pontuação_Hemoglobina', 'pa': 'Pontuação_PA', 'con': 'Pontuação_Consultas', 'peso': 'Pontuação_PesoAltura' }};
            const col = keyMap[criterio];
            const somaCriterio = dadosFiltrados.reduce((acc, d) => acc + d[col], 0);
            
            const pctCumprimento = (somaCriterio / total) * 100;
            const pctNaoAtendido = 100 - pctCumprimento;

            document.getElementById(criterio + '-val-cumprimento').textContent = pctCumprimento.toFixed(2) + '%';
            document.getElementById(criterio + '-val-naopreenchido').textContent = pctNaoAtendido.toFixed(2) + '%';

            gerarRankingIndividual(criterio);
            gerarGraficoLinhas(criterio);
        }}

        function gerarRankingUBS() {{
            const container = document.getElementById('ranking-container');
            if(!container) return;
            container.innerHTML = '';
            
            const criterios = ['Pontuação_Pés', 'Pontuação_Visitas', 'Pontuação_Hemoglobina', 'Pontuação_PA', 'Pontuação_Consultas', 'Pontuação_PesoAltura'];
            const ubsMap = {{}};

            dadosFiltrados.forEach(d => {{
                if(!ubsMap[d.UBS]) ubsMap[d.UBS] = {{ soma: 0, count: 0 }};
                let somaRow = 0;
                criterios.forEach(c => somaRow += d[c]);
                ubsMap[d.UBS].soma += (somaRow / criterios.length) * 100;
                ubsMap[d.UBS].count += 1;
            }});

            const ranking = Object.keys(ubsMap).map(ubs => {{
                const media = ubsMap[ubs].soma / ubsMap[ubs].count;
                return {{ ubs, media }};
            }}).sort((a, b) => b.media - a.media);

            ranking.forEach((r, idx) => {{
                const row = document.createElement('div');
                row.style.cssText = 'display: flex; flex-direction: column; gap: 2px; font-size: 11px; margin-bottom: 6px;';
                row.innerHTML = `
                    <div style="display: flex; justify-content: space-between; font-weight: bold; color: #323130;">
                        <span>${{idx + 1}}. ${{r.ubs}}</span>
                        <span style="color: #8B262B;">${{r.media.toFixed(2)}}%</span>
                    </div>
                    <div style="background: #F3F2F1; border-radius: 4px; height: 6px; width: 100%; overflow: hidden;">
                        <div style="background: #8B262B; height: 100%; width: ${{r.media}}%; border-radius: 4px;"></div>
                    </div>
                `;
                container.appendChild(row);
            }});
        }}

        function gerarRankingIndividual(criterio) {{
            const keyMap = {{ 'pes': 'Pontuação_Pés', 'vis': 'Pontuação_Visitas', 'hem': 'Pontuação_Hemoglobina', 'pa': 'Pontuação_PA', 'con': 'Pontuação_Consultas', 'peso': 'Pontuação_PesoAltura' }};
            const col = keyMap[criterio];

            // UBS
            const containerUbs = document.getElementById(criterio + '-ranking-ubs');
            if(containerUbs) {{
                containerUbs.innerHTML = '';
                const mapUbs = {{}};
                dadosFiltrados.forEach(d => {{
                    if(!mapUbs[d.UBS]) mapUbs[d.UBS] = {{ soma: 0, count: 0 }};
                    mapUbs[d.UBS].soma += d[col];
                    mapUbs[d.UBS].count += 1;
                }});
                const rankUbs = Object.keys(mapUbs).map(ubs => {{
                    const media = (mapUbs[ubs].soma / mapUbs[ubs].count) * 100;
                    return {{ ubs, media }};
                }}).sort((a, b) => b.media - a.media);

                rankUbs.slice(0, 5).forEach((r, idx) => {{
                    const row = document.createElement('div');
                    row.style.cssText = 'display: flex; flex-direction: column; gap: 2px; font-size: 10px; margin-bottom: 4px;';
                    row.innerHTML = `
                        <div style="display: flex; justify-content: space-between; font-weight: bold;">
                            <span>${{idx + 1}}. ${{r.ubs}}</span>
                            <span style="color: #8B262B;">${{r.media.toFixed(2)}}%</span>
                        </div>
                        <div style="background: #F3F2F1; border-radius: 3px; height: 5px; width: 100%; overflow: hidden;">
                            <div style="background: #8B262B; height: 100%; width: ${{r.media}}%; border-radius: 3px;"></div>
                        </div>
                    `;
                    containerUbs.appendChild(row);
                }});
            }}

            // Equipe
            const containerEq = document.getElementById(criterio + '-ranking-equipe');
            if(containerEq) {{
                containerEq.innerHTML = '';
                const mapEq = {{}};
                dadosFiltrados.forEach(d => {{
                    if(!mapEq[d.EQUIPE]) mapEq[d.EQUIPE] = {{ soma: 0, count: 0 }};
                    mapEq[d.EQUIPE].soma += d[col];
                    mapEq[d.EQUIPE].count += 1;
                }});
                const rankEq = Object.keys(mapEq).map(equipe => {{
                    const media = (mapEq[equipe].soma / mapEq[equipe].count) * 100;
                    return {{ equipe, media }};
                }}).sort((a, b) => b.media - a.media);

                rankEq.slice(0, 5).forEach((r, idx) => {{
                    const row = document.createElement('div');
                    row.style.cssText = 'display: flex; flex-direction: column; gap: 2px; font-size: 10px; margin-bottom: 4px;';
                    row.innerHTML = `
                        <div style="display: flex; justify-content: space-between; font-weight: bold;">
                            <span>${{idx + 1}}. ${{r.equipe}}</span>
                            <span style="color: #8B262B;">${{r.media.toFixed(2)}}%</span>
                        </div>
                        <div style="background: #F3F2F1; border-radius: 3px; height: 5px; width: 100%; overflow: hidden;">
                            <div style="background: #8B262B; height: 100%; width: ${{r.media}}%; border-radius: 3px;"></div>
                        </div>
                    `;
                    containerEq.appendChild(row);
                }});
            }}
        }}

        function gerarGraficoLinhas(criterio) {{
            const keyMap = {{ 'pes': 'Pontuação_Pés', 'vis': 'Pontuação_Visitas', 'hem': 'Pontuação_Hemoglobina', 'pa': 'Pontuação_PA', 'con': 'Pontuação_Consultas', 'peso': 'Pontuação_PesoAltura' }};
            const col = keyMap[criterio];
            const canvasId = criterio + '-canvas-linhas';
            const ctx = document.getElementById(canvasId);
            if(!ctx) return;

            const mapData = {{}};
            dadosOriginais.forEach(d => {{
                const dt = d.DATA_STR;
                if(!dt) return;
                if(!mapData[dt]) mapData[dt] = {{ soma: 0, count: 0 }};
                mapData[dt].soma += d[col];
                mapData[dt].count += 1;
            }});

            const labels = Object.keys(mapData).sort();
            const valores = labels.map(dt => (mapData[dt].soma / mapData[dt].count) * 100);

            if(charts[criterio]) {{
                charts[criterio].destroy();
            }}

            charts[criterio] = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels.map(l => {{
                        const p = l.split('-');
                        return p.length === 3 ? `${{p[2]}}/${{p[1]}}/${{p[0]}}` : l;
                    }}),
                    datasets: [{{
                        label: 'Cumprimento (%)',
                        data: valores,
                        borderColor: '#8B262B',
                        backgroundColor: 'rgba(139, 38, 43, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.2
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{ y: {{ min: 0, max: 100 }} }}
                }}
            }});
        }}

        document.addEventListener("DOMContentLoaded", () => {{ atualizarEquipes(); filtrarDados(); }});
    </script>
</body>
</html>
"""

with open(caminho_saida, "w", encoding="utf-8") as f:
  f.write(html_content)

print(f"Relatório de Diabéticos gerado com sucesso em: {caminho_saida}")