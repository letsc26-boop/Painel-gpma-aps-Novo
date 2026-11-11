import base64
import glob
import os
import numpy as np
import pandas as pd

# =========================================================
# 1. DEFINIR CAMINHOS E DIRETÓRIO PARA HIPERTENSOS
# =========================================================
pasta_trabalho = r"W:\GPMA\NCAIS\Residência\Letícia Stefany Costa\Relatorio indicadores de saúde\hipertensão\arquivos csv"
caminho_saida = r"W:\GPMA\NCAIS\Residência\Letícia Stefany Costa\Relatorio indicadores de saúde\hipertensão\Relatorio_PowerBI_Hipertensos.html"

if not os.path.exists(pasta_trabalho):
  os.makedirs(pasta_trabalho, exist_ok=True)

arquivos_csv = glob.glob(os.path.join(pasta_trabalho, "*.csv"))

if not arquivos_csv:
  print(f"Erro: Nenhum ficheiro CSV encontrado em: {pasta_trabalho}")
  exit()

print(f"=== A LER E UNIFICAR OS {len(arquivos_csv)} FICHEIROS DE HIPERTENSOS ===")


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


def limpar_e_converter_num(serie):
  if serie is None:
    return pd.Series([np.nan])
  s = serie.astype(str).str.replace(",", ".").str.strip()
  s = s.replace(["-", "nan", "None", "", "0"], np.nan)
  return pd.to_numeric(s, errors="coerce")


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
      if "1ªvisita" in c_lower or "1visita" in c_lower:
        temp_df = temp_df.rename(columns={c: "Data1ªVisita"})
      elif "2ªvisita" in c_lower or "2visita" in c_lower:
        temp_df = temp_df.rename(columns={c: "Data2ªVisita"})

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

# 2. Conversão e Harmonização Segura de Colunas
colunas_data = [
    "DATA",
    "Data da última consulta",
    "Data da última medição de pressão arterial",
    "Data1ªVisita",
    "Data2ªVisita",
]

for col in colunas_data:
  col_match = next((c for c in df.columns if col.lower() in c.lower()), None)
  if col_match:
    df[col] = limpar_e_converter_data(df[col_match])
    if col_match != col and col not in df.columns:
      df = df.rename(columns={col_match: col})
  else:
    df[col] = pd.NaT

# Mapeamento flexível de Peso e Altura numéricos
col_peso = next(
    (
        c
        for c in df.columns
        if "peso" in c.lower()
        and "última" in c.lower()
        and "data" not in c.lower()
    ),
    None,
)
col_alt = next(
    (
        c
        for c in df.columns
        if "altura" in c.lower()
        and "última" in c.lower()
        and "data" not in c.lower()
    ),
    None,
)

df["Última medição de peso"] = (
    limpar_e_converter_num(df[col_peso]) if col_peso else np.nan
)
df["Última medição de altura"] = (
    limpar_e_converter_num(df[col_alt]) if col_alt else np.nan
)

# Varredura dinâmica de todas as colunas de data de peso/altura possíveis nos CSVs
dt_peso_alt_conjunta = next(
    (
        df[c]
        for c in df.columns
        if (
            "peso" in c.lower()
            and "altura" in c.lower()
            and "data" in c.lower()
        )
    ),
    pd.Series([pd.NaT] * len(df)),
)
dt_peso_sep = next(
    (
        df[c]
        for c in df.columns
        if (
            "peso" in c.lower()
            and "data" in c.lower()
            and "altura" not in c.lower()
        )
    ),
    pd.Series([pd.NaT] * len(df)),
)
dt_alt_sep = next(
    (
        df[c]
        for c in df.columns
        if (
            "altura" in c.lower()
            and "data" in c.lower()
            and "peso" not in c.lower()
        )
    ),
    pd.Series([pd.NaT] * len(df)),
)

dt_conj_conv = limpar_e_converter_data(dt_peso_alt_conjunta)
dt_p_conv = limpar_e_converter_data(dt_peso_sep)
dt_a_conv = limpar_e_converter_data(dt_alt_sep)

df["Data_Peso_Altura_Final"] = dt_conj_conv.fillna(dt_p_conv).fillna(dt_a_conv)

# Data de referência por linha (DATA da foto do relatório ou Hoje)
df["Data_Atual"] = df["DATA"].fillna(pd.to_datetime("today"))


# 3. REGRAS DE PONTUAÇÃO POWER BI DAX / M EXACTAS
def dentro(d_serie, ref_serie, dias):
  return (
      d_serie.notna()
      & ((ref_serie - d_serie).dt.days <= dias)
      & ((ref_serie - d_serie).dt.days >= 0)
  )


# P_Consulta (1 = Dentro 180 dias | 0 = Fora / Ausente)
df["Pontuação Consultas"] = np.where(
    dentro(df["Data da última consulta"], df["Data_Atual"], 180), 1, 0
)

# P_PA (2 = Null | 1 = Dentro 180 dias | 0 = Fora)
df["Pontuação PA"] = np.select(
    [
        df["Data da última medição de pressão arterial"].isna(),
        dentro(df["Data da última medição de pressão arterial"], df["Data_Atual"], 180),
    ],
    [2, 1],
    default=0,
)

# P_Peso (2 = Peso Null ou Altura Null ou Data Null | 1 = Dentro 365 dias | 0 = Fora)
cond_peso_null = (
    df["Última medição de peso"].isna()
    | df["Última medição de altura"].isna()
    | df["Data_Peso_Altura_Final"].isna()
)
cond_peso_ok = dentro(df["Data_Peso_Altura_Final"], df["Data_Atual"], 365)
df["Pontuação Peso e Altura"] = np.select(
    [cond_peso_null, cond_peso_ok], [2, 1], default=0
)

# P_Visitas (0 = Sem visita / Fora do prazo | 1 = Duas visitas válidas | 2 = 1ª Visita feita há <= 365 dias, sem 2ª)
d1 = df["Data1ªVisita"]
d2 = df["Data2ªVisita"]
ref = df["Data_Atual"]

diff_d2_d1 = (d2 - d1).dt.days
diff_ref_d2 = (ref - d2).dt.days
diff_ref_d1 = (ref - d1).dt.days

cond_v1 = (
    d1.notna()
    & d2.notna()
    & (diff_d2_d1 >= 30)
    & (diff_d2_d1 <= 365)
    & (diff_ref_d2 <= 365)
)
cond_v2 = d1.notna() & d2.isna() & (diff_ref_d1 <= 365)

df["Pontuação Visitas"] = np.select(
    [d1.isna(), cond_v1, cond_v2], [0, 1, 2], default=0
)

# 4. Preparação dos dados JSON para o JavaScript
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
    "Pontuação Consultas",
    "Pontuação PA",
    "Pontuação Peso e Altura",
    "Pontuação Visitas",
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

# Carregar imagem GPMA
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
    else '<div style="font-weight:bold; color:#1E3A8A; font-size:12px;'
    ' text-align:center;">GPMA - APS</div>'
)

# 5. Geração do HTML Interativo Final Completo
html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Monitoramento - Hipertensos</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #EFEFEF; color: #323130; margin: 0; padding: 0; height: 100vh; overflow: hidden; }}
        .app-container {{ display: flex; height: 100vh; width: 100vw; }}
        
        .sidebar {{ width: 220px; background-color: #1E3A8A; color: white; display: flex; flex-direction: column; padding: 12px; box-shadow: 2px 0 5px rgba(0,0,0,0.1); z-index: 10; overflow-y: auto; flex-shrink: 0; }}
        
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
        .nav-item:hover, .nav-item.active {{ background-color: white; color: #1E3A8A; }}
        .nav-item svg {{ width: 16px; height: 16px; fill: currentColor; flex-shrink: 0; }}
        
        .btn-limpar {{ margin-top: 10px; background-color: #2563EB; color: white; border: 1px solid white; padding: 6px; border-radius: 4px; font-size: 11px; font-weight: bold; cursor: pointer; text-transform: uppercase; text-align: center; }}
        .btn-limpar:hover {{ background-color: white; color: #1E3A8A; }}

        .main-content {{ flex: 1; background-color: #F4F5F7; padding: 12px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }}
        
        .header-container {{ background-color: #1E3A8A; color: white; padding: 10px 15px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header-title {{ font-size: 15px; font-weight: bold; text-transform: uppercase; }}
        .header-subtitle {{ font-size: 10px; opacity: 0.9; margin-top: 2px; max-width: 600px; }}
        .top-buttons {{ display: flex; gap: 6px; }}
        .btn-pb {{ background-color: #2563EB; color: white; border: 1px solid white; padding: 5px 10px; border-radius: 4px; font-size: 10px; font-weight: bold; cursor: pointer; text-transform: uppercase; }}
        .btn-pb:hover {{ background-color: white; color: #1E3A8A; }}

        .cards-container {{ display: flex; gap: 10px; }}
        .card {{ background: white; border-radius: 6px; padding: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1; text-align: center; border-top: 4px solid #1E3A8A; }}
        .card-title {{ font-size: 9px; color: #605E5C; text-transform: uppercase; font-weight: bold; }}
        .card-value {{ font-size: 18px; font-weight: bold; color: #1E3A8A; margin-top: 2px; }}

        .main-grid {{ display: flex; gap: 10px; flex: 1; }}
        .box-left {{ background: white; border-radius: 6px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1.2; display: flex; flex-direction: column; gap: 10px; }}
        .box-right {{ background: white; border-radius: 6px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1.8; overflow-y: auto; max-height: 440px; }}
        .section-title {{ font-size: 11px; color: #1E3A8A; font-weight: bold; text-transform: uppercase; margin-bottom: 8px; border-bottom: 2px solid #F3F2F1; padding-bottom: 4px; }}
        
        .metric-row {{ display: flex; align-items: center; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #F3F2F1; font-size: 11px; cursor: pointer; }}
        .metric-row:hover {{ background-color: #FAF9F8; }}
        .metric-left {{ display: flex; align-items: center; gap: 10px; max-width: 75%; }}
        .metric-icon {{ width: 22px; height: 22px; fill: #1E3A8A; flex-shrink: 0; }}
        .metric-label {{ color: #323130; line-height: 1.2; }}
        .metric-val {{ font-weight: bold; color: #1E3A8A; font-size: 13px; }}

        .page-view {{ display: none; flex-direction: column; gap: 10px; flex: 1; }}
        .page-view.active {{ display: flex; }}
        .sub-grid {{ display: flex; gap: 10px; flex: 1; }}
        .sub-col {{ display: flex; flex-direction: column; gap: 10px; flex: 1; }}
        .chart-box {{ background: white; border-radius: 6px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1; overflow-y: auto; max-height: 230px; }}
        .canvas-holder {{ position: relative; width: 100%; height: 160px; }}
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
                <button id="nav-vis" class="nav-item" onclick="mudarPagina('vis')"><svg viewBox="0 0 24 24"><path d="M12 3L2 12H5V20H10V14H14V20H19V12H22L12 3Z"/></svg>Visitas Domiciliares</button>
                <button id="nav-pa" class="nav-item" onclick="mudarPagina('pa')"><svg viewBox="0 0 24 24"><path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z"/></svg>Pressão Arterial</button>
                <button id="nav-peso" class="nav-item" onclick="mudarPagina('peso')"><svg viewBox="0 0 24 24"><path d="M19 3H5C3.9 3 3 3.9 3 5V19C3 20.1 3.9 21 5 21H19C20.1 21 21 20.1 21 19V5C21 3.9 20.1 3 19 3M12 6C13.66 6 15 7.34 15 9C15 10.66 13.66 12 12 12C10.34 12 9 10.66 9 9C9 7.34 10.34 6 12 6M16 16H8V15C8 13.67 10.67 13 12 13C13.33 13 16 13.67 16 15V16Z"/></svg>Peso e Altura</button>
                <button id="nav-con" class="nav-item" onclick="mudarPagina('con')"><svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12C2 17.52 6.48 22 12 22C17.52 22 22 17.52 22 12C22 6.48 17.52 2 12 2M10 17L5 12L6.41 10.59L10 14.17L17.59 6.58L19 8L10 17Z"/></svg>Consultas Médica/Enf.</button>
            </div>

            <div class="btn-limpar" onclick="limparFiltros()">Limpar Filtros</div>
        </div>

        <!-- CONTEÚDO PRINCIPAL -->
        <div class="main-content">

            <!-- PÁGINA 1: VISÃO GERAL -->
            <div id="view-geral" class="page-view active">
                <div class="header-container">
                    <div>
                        <div class="header-title">Monitoramento — Cuidado da Pessoa com Hipertensão</div>
                        <div class="header-subtitle">Tem como objetivo avaliar o acesso e monitoramento efetivo do cuidado integral à saúde das pessoas com hipertensão, com incentivo à captação precoce e acompanhamento continuado na APS.</div>
                    </div>
                </div>

                <div class="cards-container">
                    <div class="card">
                        <div class="card-title">Total de Hipertensos</div>
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
                            <div class="filter-label" style="color: #1E3A8A; font-weight: bold;">Data de Referência</div>
                            <select id="filtro-data" class="filter-select" onchange="filtrarDados();" style="border: 1px solid #1E3A8A;">
                                <option value="TODAS">Todas as Datas</option>
                                {opcoes_datas_html}
                            </select>
                        </div>
                    </div>

                    <div class="box-right">
                        <div class="section-title">% de Não Cumprimento das Boas Práticas</div>
                        
                        <div class="metric-row" onclick="mudarPagina('vis')">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M12 3L2 12H5V20H10V14H14V20H19V12H22L12 3Z"/></svg>
                                <div class="metric-label">Ter pelo menos 02 (duas) visitas domiciliares realizadas por ACS/TACS, com intervalo mínimo de 30 (trinta) dias, nos últimos 12 (doze) meses.</div>
                            </div>
                            <div id="nao-vis" class="metric-val">0.00%</div>
                        </div>

                        <div class="metric-row" onclick="mudarPagina('pa')">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z"/></svg>
                                <div class="metric-label">Ter pelo menos 01 (um) registro de aferição de pressão arterial realizado nos últimos 06 (seis) meses.</div>
                            </div>
                            <div id="nao-pa" class="metric-val">0.00%</div>
                        </div>

                        <div class="metric-row" onclick="mudarPagina('peso')">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M19 3H5C3.9 3 3 3.9 3 5V19C3 20.1 3.9 21 5 21H19C20.1 21 21 20.1 21 19V5C21 3.9 20.1 3 19 3M12 6C13.66 6 15 7.34 15 9C15 10.66 13.66 12 12 12C10.34 12 9 10.66 9 9C9 7.34 10.34 6 12 6M16 16H8V15C8 13.67 10.67 13 12 13C13.33 13 16 13.67 16 15V16Z"/></svg>
                                <div class="metric-label">Ter pelo menos 01 (um) registro simultâneo de peso e altura realizado nos últimos 12 (doze) meses.</div>
                            </div>
                            <div id="nao-peso" class="metric-val">0.00%</div>
                        </div>

                        <div class="metric-row" onclick="mudarPagina('con')" style="border-bottom: none;">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12C2 17.52 6.48 22 12 22C17.52 22 22 17.52 22 12C22 6.48 17.52 2 12 2M10 17L5 12L6.41 10.59L10 14.17L17.59 6.58L19 8L10 17Z"/></svg>
                                <div class="metric-label">Ter pelo menos 01 (uma) consulta presencial ou remota realizada por médica(o) ou enfermeira(o), nos últimos 06 (seis) meses.</div>
                            </div>
                            <div id="nao-con" class="metric-val">0.00%</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- PÁGINAS INDIVIDUAIS DE BOAS PRÁTICAS -->
            <!-- 1. VISITAS -->
            <div id="view-vis" class="page-view">
                <div class="header-container">
                    <div>
                        <div class="header-title">Monitoramento — Cuidado da Pessoa com Hipertensão: VISITAS DOMICILIARES</div>
                        <div class="header-subtitle"><b>BOA PRÁTICA:</b> Ter pelo menos 02 (duas) visitas domiciliares realizadas por ACS/TACS, com intervalo mínimo de 30 dias, nos últimos 12 meses.</div>
                    </div>
                    <div class="top-buttons"><button class="btn-pb" onclick="mudarPagina('geral')">Voltar</button></div>
                </div>
                <div class="cards-container">
                    <div class="card"><div class="card-title">Cumprimento</div><div id="vis-val-cumprimento" class="card-value">0.00%</div></div>
                    <div class="card"><div class="card-title">Ainda dentro do prazo</div><div id="vis-val-foraprazo" class="card-value">0.00%</div></div>
                    <div class="card"><div class="card-title">Fora do Prazo / Sem Visita</div><div id="vis-val-naopreenchido" class="card-value">0.00%</div></div>
                </div>
                <div class="sub-grid">
                    <div class="sub-col" style="flex: 1.2;">
                        <div class="chart-box" style="max-height: 480px; display: flex; flex-direction: column;">
                            <div class="section-title">Evolução ao Longo do Tempo</div>
                            <div class="canvas-holder"><canvas id="vis-canvas-linhas"></canvas></div>
                            <div style="border-top: 2px solid #F3F2F1; padding-top: 8px; margin-top: 8px;">
                                <div class="filter-label" style="color: #1E3A8A; font-weight: bold;">Data de Referência</div>
                                <select id="vis-filtro-data" class="filter-select" onchange="filtrarDados();"><option value="TODAS">Todas as Datas</option>{opcoes_datas_html}</select>
                            </div>
                        </div>
                    </div>
                    <div class="sub-col" style="flex: 1.8;">
                        <div class="chart-box"><div class="section-title">Ranking por UBS</div><div id="vis-ranking-ubs" style="display:flex; flex-direction:column; gap:6px;"></div></div>
                        <div class="chart-box"><div class="section-title">Ranking por Equipe</div><div id="vis-ranking-equipe" style="display:flex; flex-direction:column; gap:6px;"></div></div>
                    </div>
                </div>
            </div>

            <!-- 2. PRESSÃO ARTERIAL -->
            <div id="view-pa" class="page-view">
                <div class="header-container">
                    <div>
                        <div class="header-title">Monitoramento — Cuidado da Pessoa com Hipertensão: PRESSÃO ARTERIAL</div>
                        <div class="header-subtitle"><b>BOA PRÁTICA:</b> Ter pelo menos 01 (um) registro de aferição de pressão arterial realizado nos últimos 06 meses.</div>
                    </div>
                    <div class="top-buttons"><button class="btn-pb" onclick="mudarPagina('geral')">Voltar</button></div>
                </div>
                <div class="cards-container">
                    <div class="card"><div class="card-title">Cumprimento</div><div id="pa-val-cumprimento" class="card-value">0.00%</div></div>
                    <div class="card"><div class="card-title">Fora do Prazo</div><div id="pa-val-foraprazo" class="card-value">0.00%</div></div>
                    <div class="card"><div class="card-title">Não Preenchido</div><div id="pa-val-naopreenchido" class="card-value">0.00%</div></div>
                </div>
                <div class="sub-grid">
                    <div class="sub-col" style="flex: 1.2;">
                        <div class="chart-box" style="max-height: 480px; display: flex; flex-direction: column;">
                            <div class="section-title">Evolução ao Longo do Tempo</div>
                            <div class="canvas-holder"><canvas id="pa-canvas-linhas"></canvas></div>
                            <div style="border-top: 2px solid #F3F2F1; padding-top: 8px; margin-top: 8px;">
                                <div class="filter-label" style="color: #1E3A8A; font-weight: bold;">Data de Referência</div>
                                <select id="pa-filtro-data" class="filter-select" onchange="filtrarDados();"><option value="TODAS">Todas as Datas</option>{opcoes_datas_html}</select>
                            </div>
                        </div>
                    </div>
                    <div class="sub-col" style="flex: 1.8;">
                        <div class="chart-box"><div class="section-title">Ranking por UBS</div><div id="pa-ranking-ubs" style="display:flex; flex-direction:column; gap:6px;"></div></div>
                        <div class="chart-box"><div class="section-title">Ranking por Equipe</div><div id="pa-ranking-equipe" style="display:flex; flex-direction:column; gap:6px;"></div></div>
                    </div>
                </div>
            </div>

            <!-- 3. PESO E ALTURA -->
            <div id="view-peso" class="page-view">
                <div class="header-container">
                    <div>
                        <div class="header-title">Monitoramento — Cuidado da Pessoa com Hipertensão: PESO E ALTURA</div>
                        <div class="header-subtitle"><b>BOA PRÁTICA:</b> Ter pelo menos 01 (um) registro simultâneo de peso e altura nos últimos 12 meses.</div>
                    </div>
                    <div class="top-buttons"><button class="btn-pb" onclick="mudarPagina('geral')">Voltar</button></div>
                </div>
                <div class="cards-container">
                    <div class="card"><div class="card-title">Cumprimento</div><div id="peso-val-cumprimento" class="card-value">0.00%</div></div>
                    <div class="card"><div class="card-title">Fora do Prazo</div><div id="peso-val-foraprazo" class="card-value">0.00%</div></div>
                    <div class="card"><div class="card-title">Não Preenchido</div><div id="peso-val-naopreenchido" class="card-value">0.00%</div></div>
                </div>
                <div class="sub-grid">
                    <div class="sub-col" style="flex: 1.2;">
                        <div class="chart-box" style="max-height: 480px; display: flex; flex-direction: column;">
                            <div class="section-title">Evolução ao Longo do Tempo</div>
                            <div class="canvas-holder"><canvas id="peso-canvas-linhas"></canvas></div>
                            <div style="border-top: 2px solid #F3F2F1; padding-top: 8px; margin-top: 8px;">
                                <div class="filter-label" style="color: #1E3A8A; font-weight: bold;">Data de Referência</div>
                                <select id="peso-filtro-data" class="filter-select" onchange="filtrarDados();"><option value="TODAS">Todas as Datas</option>{opcoes_datas_html}</select>
                            </div>
                        </div>
                    </div>
                    <div class="sub-col" style="flex: 1.8;">
                        <div class="chart-box"><div class="section-title">Ranking por UBS</div><div id="peso-ranking-ubs" style="display:flex; flex-direction:column; gap:6px;"></div></div>
                        <div class="chart-box"><div class="section-title">Ranking por Equipe</div><div id="peso-ranking-equipe" style="display:flex; flex-direction:column; gap:6px;"></div></div>
                    </div>
                </div>
            </div>

            <!-- 4. CONSULTAS -->
            <div id="view-con" class="page-view">
                <div class="header-container">
                    <div>
                        <div class="header-title">Monitoramento — Cuidado da Pessoa com Hipertensão: CONSULTAS</div>
                        <div class="header-subtitle"><b>BOA PRÁTICA:</b> Ter pelo menos 01 (uma) consulta presencial ou remota por médica(o) ou enfermeira(o) nos últimos 06 meses.</div>
                    </div>
                    <div class="top-buttons"><button class="btn-pb" onclick="mudarPagina('geral')">Voltar</button></div>
                </div>
                <div class="cards-container">
                    <div class="card"><div class="card-title">Cumprimento</div><div id="con-val-cumprimento" class="card-value">0.00%</div></div>
                    <div class="card"><div class="card-title">Fora do Prazo / Não Preenchido</div><div id="con-val-foraprazo" class="card-value">0.00%</div></div>
                </div>
                <div class="sub-grid">
                    <div class="sub-col" style="flex: 1.2;">
                        <div class="chart-box" style="max-height: 480px; display: flex; flex-direction: column;">
                            <div class="section-title">Evolução ao Longo do Tempo</div>
                            <div class="canvas-holder"><canvas id="con-canvas-linhas"></canvas></div>
                            <div style="border-top: 2px solid #F3F2F1; padding-top: 8px; margin-top: 8px;">
                                <div class="filter-label" style="color: #1E3A8A; font-weight: bold;">Data de Referência</div>
                                <select id="con-filtro-data" class="filter-select" onchange="filtrarDados();"><option value="TODAS">Todas as Datas</option>{opcoes_datas_html}</select>
                            </div>
                        </div>
                    </div>
                    <div class="sub-col" style="flex: 1.8;">
                        <div class="chart-box"><div class="section-title">Ranking por UBS</div><div id="con-ranking-ubs" style="display:flex; flex-direction:column; gap:6px;"></div></div>
                        <div class="chart-box"><div class="section-title">Ranking por Equipe</div><div id="con-ranking-equipe" style="display:flex; flex-direction:column; gap:6px;"></div></div>
                    </div>
                </div>
            </div>

        </div>
    </div>

    <script>
        const dadosGlobais = {dados_json};
        let dadosFiltrados = [...dadosGlobais];
        let activeView = 'geral';
        const chartInstances = {{}};

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
            const ubsSel = document.getElementById('filtro-ubs').value;
            const eqSelect = document.getElementById('filtro-equipe');
            eqSelect.innerHTML = '<option value="TODAS">Todas as Equipes</option>';

            const equipes = [...new Set(dadosGlobais
                .filter(d => ubsSel === 'TODAS' || d.UBS === ubsSel)
                .map(d => d.EQUIPE))].sort();

            equipes.forEach(eq => {{
                const opt = document.createElement('option');
                opt.value = eq;
                opt.textContent = eq;
                eqSelect.appendChild(opt);
            }});
        }}

        function limparFiltros() {{
            document.getElementById('filtro-ubs').value = 'TODAS';
            atualizarEquipes();
            document.getElementById('filtro-equipe').value = 'TODAS';
            document.getElementById('filtro-data').value = 'TODAS';
            
            ['vis', 'pa', 'peso', 'con'].forEach(k => {{
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

            dadosFiltrados = dadosGlobais.filter(d => {{
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
                ['vis', 'pa', 'peso', 'con'].forEach(k => {{
                    const el = document.getElementById('nao-' + k);
                    if(el) el.textContent = '0.00%';
                }});
                gerarRankingUBS();
                return;
            }}

            const criterios = ['Pontuação Visitas', 'Pontuação PA', 'Pontuação Peso e Altura', 'Pontuação Consultas'];
            let somaTotalPraticas = 0;

            criterios.forEach(col => {{
                const somaCol = dadosFiltrados.reduce((acc, d) => acc + (d[col] === 1 ? 1 : 0), 0);
                somaTotalPraticas += somaCol;
            }});

            const mediaGeral = (somaTotalPraticas / (total * criterios.length)) * 100;
            document.getElementById('val-media-praticas').textContent = mediaGeral.toFixed(2) + '%';

            const mapChaves = {{ 'vis': 'Pontuação Visitas', 'pa': 'Pontuação PA', 'peso': 'Pontuação Peso e Altura', 'con': 'Pontuação Consultas' }};
            
            Object.keys(mapChaves).forEach(k => {{
                const col = mapChaves[k];
                const somaC = dadosFiltrados.reduce((acc, d) => acc + (d[col] === 1 ? 1 : 0), 0);
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
            const keyMap = {{ 'vis': 'Pontuação Visitas', 'pa': 'Pontuação PA', 'peso': 'Pontuação Peso e Altura', 'con': 'Pontuação Consultas' }};
            const col = keyMap[criterio];

            const c1 = dadosFiltrados.reduce((acc, d) => acc + (d[col] === 1 ? 1 : 0), 0);
            const c2 = dadosFiltrados.reduce((acc, d) => acc + (d[col] === 2 ? 1 : 0), 0);
            const c0 = dadosFiltrados.reduce((acc, d) => acc + (d[col] === 0 ? 1 : 0), 0);

            const pctCumprimento = (c1 / total) * 100;
            const pctForaPrazo = (c2 / total) * 100;
            const pctNaoPreenchido = (c0 / total) * 100;

            document.getElementById(criterio + '-val-cumprimento').textContent = pctCumprimento.toFixed(2) + '%';
            
            const elFora = document.getElementById(criterio + '-val-foraprazo');
            if(elFora) elFora.textContent = pctForaPrazo.toFixed(2) + '%';

            const elNao = document.getElementById(criterio + '-val-naopreenchido');
            if(elNao) elNao.textContent = pctNaoPreenchido.toFixed(2) + '%';

            gerarRankingIndividual(criterio);
            gerarGraficoLinhas(criterio);
        }}

        function gerarRankingUBS() {{
            const container = document.getElementById('ranking-container');
            if(!container) return;
            container.innerHTML = '';
            
            const criterios = ['Pontuação Visitas', 'Pontuação PA', 'Pontuação Peso e Altura', 'Pontuação Consultas'];
            const ubsMap = {{}};

            dadosFiltrados.forEach(d => {{
                if(!ubsMap[d.UBS]) ubsMap[d.UBS] = {{ soma: 0, count: 0 }};
                let somaRow = 0;
                criterios.forEach(c => {{ if(d[c] === 1) somaRow += 1; }});
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
                        <span style="color: #1E3A8A;">${{r.media.toFixed(2)}}%</span>
                    </div>
                    <div style="background: #F3F2F1; border-radius: 4px; height: 6px; width: 100%; overflow: hidden;">
                        <div style="background: #1E3A8A; height: 100%; width: ${{r.media}}%; border-radius: 4px;"></div>
                    </div>
                `;
                container.appendChild(row);
            }});
        }}

        function gerarRankingIndividual(criterio) {{
            const keyMap = {{ 'vis': 'Pontuação Visitas', 'pa': 'Pontuação PA', 'peso': 'Pontuação Peso e Altura', 'con': 'Pontuação Consultas' }};
            const col = keyMap[criterio];

            // UBS
            const containerUbs = document.getElementById(criterio + '-ranking-ubs');
            if(containerUbs) {{
                containerUbs.innerHTML = '';
                const mapUbs = {{}};
                dadosFiltrados.forEach(d => {{
                    if(!mapUbs[d.UBS]) mapUbs[d.UBS] = {{ soma: 0, count: 0 }};
                    if(d[col] === 1) mapUbs[d.UBS].soma += 1;
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
                            <span style="color: #1E3A8A;">${{r.media.toFixed(2)}}%</span>
                        </div>
                        <div style="background: #F3F2F1; border-radius: 3px; height: 5px; width: 100%; overflow: hidden;">
                            <div style="background: #1E3A8A; height: 100%; width: ${{r.media}}%; border-radius: 3px;"></div>
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
                    if(d[col] === 1) mapEq[d.EQUIPE].soma += 1;
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
                            <span style="color: #1E3A8A;">${{r.media.toFixed(2)}}%</span>
                        </div>
                        <div style="background: #F3F2F1; border-radius: 3px; height: 5px; width: 100%; overflow: hidden;">
                            <div style="background: #1E3A8A; height: 100%; width: ${{r.media}}%; border-radius: 3px;"></div>
                        </div>
                    `;
                    containerEq.appendChild(row);
                }});
            }}
        }}

        function gerarGraficoLinhas(criterio) {{
            const keyMap = {{ 'vis': 'Pontuação Visitas', 'pa': 'Pontuação PA', 'peso': 'Pontuação Peso e Altura', 'con': 'Pontuação Consultas' }};
            const col = keyMap[criterio];
            const canvasId = criterio + '-canvas-linhas';
            const ctx = document.getElementById(canvasId);
            if(!ctx) return;

            const mapData = {{}};
            dadosGlobais.forEach(d => {{
                const dt = d.DATA_STR;
                if(!dt) return;
                if(!mapData[dt]) mapData[dt] = {{ soma: 0, count: 0 }};
                if(d[col] === 1) mapData[dt].soma += 1;
                mapData[dt].count += 1;
            }});

            const labels = Object.keys(mapData).sort();
            const valores = labels.map(dt => (mapData[dt].soma / mapData[dt].count) * 100);

            if(chartInstances[criterio]) {{
                chartInstances[criterio].destroy();
            }}

            chartInstances[criterio] = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels.map(l => {{
                        const p = l.split('-');
                        return p.length === 3 ? `${{p[2]}}/${{p[1]}}/${{p[0]}}` : l;
                    }}),
                    datasets: [{{
                        label: 'Cumprimento (%)',
                        data: valores,
                        borderColor: '#1E3A8A',
                        backgroundColor: 'rgba(30, 58, 138, 0.1)',
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

print(f"Relatório de Hipertensos gerado com sucesso em: {caminho_saida}")