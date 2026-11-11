import base64
import glob
import os
import numpy as np
import pandas as pd

# =========================================================
# 1. DEFINIR CAMINHOS E DIRETÓRIO PARA DESENVOLVIMENTO INFANTIL
# =========================================================
pasta_trabalho = r"W:\GPMA\NCAIS\Residência\Letícia Stefany Costa\Relatorio indicadores de saúde\desenvolvimento infantil\arquivos csv"
caminho_saida = r"W:\GPMA\NCAIS\Residência\Letícia Stefany Costa\Relatorio indicadores de saúde\desenvolvimento infantil\Relatorio_PowerBI_Desenvolvimento_Infantil.html"

if not os.path.exists(pasta_trabalho):
  os.makedirs(pasta_trabalho, exist_ok=True)

arquivos_csv = glob.glob(os.path.join(pasta_trabalho, "*.csv"))

if not arquivos_csv:
  print(f"Erro: Nenhum ficheiro CSV encontrado em: {pasta_trabalho}")
  exit()

print(
    f"=== A LER E UNIFICAR OS {len(arquivos_csv)} FICHEIROS DE DESENVOLVIMENTO"
    " INFANTIL ==="
)


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

# 2. Harmonização e Tratamento de Datas
if "DATA" in df.columns:
  df["DATA"] = limpar_e_converter_data(df["DATA"])
else:
  df["DATA"] = pd.to_datetime("today")

df["Data_Atual"] = df["DATA"].fillna(pd.to_datetime("today"))

# 3. CONFORME NOTA METODOLÓGICA C2: Cada boa prática vale 20 pontos (Total máximo = 100 pontos por criança)
def converter_pontos_criterio(col):
  if col in df.columns:
    return np.where(df[col].astype(str).str.upper() == "SIM", 20, 0)
  return np.zeros(len(df))


df["Pontuação_A"] = converter_pontos_criterio("Criterio_A_1Consulta30Dias")
df["Pontuação_B"] = converter_pontos_criterio("Criterio_B_9Consultas2Anos")
df["Pontuação_C"] = converter_pontos_criterio("Criterio_C_9PesosAlturas")
df["Pontuação_D"] = converter_pontos_criterio("Criterio_D_2VisitasDom")
df["Pontuação_E"] = converter_pontos_criterio("Criterio_E_VacinasCompletas")

df["Pontuação_Total"] = (
    df["Pontuação_A"]
    + df["Pontuação_B"]
    + df["Pontuação_C"]
    + df["Pontuação_D"]
    + df["Pontuação_E"]
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
    "Pontuação_A",
    "Pontuação_B",
    "Pontuação_C",
    "Pontuação_D",
    "Pontuação_E",
    "Pontuação_Total",
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
    else '<div style="font-weight:bold; color:#065F46; font-size:12px;'
    ' text-align:center;">GPMA - APS</div>'
)

secoes_individuais = [
    (
        "a",
        "1ª CONSULTA ATÉ 30 DIAS (A)",
        (
            "Ter a 1ª consulta presencial realizada por médica(o) ou"
            " enfermeira(o), até o 30º dia de vida. (Peso: 20 pts)"
        ),
    ),
    (
        "b",
        "09 CONSULTAS ATÉ 2 ANOS (B)",
        (
            "Ter pelo menos 09 consultas presenciais ou remotas realizadas até"
            " dois anos de vida. (Peso: 20 pts)"
        ),
    ),
    (
        "c",
        "09 REGISTROS DE PESO E ALTURA (C)",
        (
            "Ter pelo menos 09 registros simultâneos de peso e altura até os"
            " dois anos de vida. (Peso: 20 pts)"
        ),
    ),
    (
        "d",
        "VISITAS DOMICILIARES ACS (D)",
        (
            "Ter pelo menos 02 visitas domiciliares por ACS/TACS (1ª até 30 dias"
            " e 2ª até 6 meses). (Peso: 20 pts)"
        ),
    ),
    (
        "e",
        "VACINAS RECOMENDADAS (E)",
        (
            "Vacinas essenciais completas conforme o calendário infantil"
            " recomendado. (Peso: 20 pts)"
        ),
    ),
]

html_secoes_abafas = ""
for c, titulo, sub in secoes_individuais:
  html_secoes_abafas += f"""
    <div id="view-{c}" class="page-view">
        <div class="header-container">
            <div>
                <div class="header-title">Desenvolvimento Infantil: {titulo}</div>
                <div class="header-subtitle"><b>BOA PRÁTICA:</b> {sub}</div>
            </div>
            <div class="top-buttons"><button class="btn-pb" onclick="mudarPagina('geral')">Voltar</button></div>
        </div>
        <div class="cards-container">
            <div class="card"><div class="card-title">Cumprimento (Média Ponderada)</div><div id="{c}-val-cumprimento" class="card-value">0.00%</div></div>
            <div class="card"><div class="card-title">Não Atendido</div><div id="{c}-val-naopreenchido" class="card-value">0.00%</div></div>
        </div>
        <div class="sub-grid">
            <div class="sub-col" style="flex: 1.2;">
                <div class="chart-box-large">
                    <div class="section-title">Evolução ao Longo do Tempo</div>
                    <div class="canvas-holder"><canvas id="{c}-canvas-linhas"></canvas></div>
                    <div style="border-top: 2px solid #E5E7EB; padding-top: 8px; margin-top: auto;">
                        <div class="filter-label" style="color: #065F46; font-weight: bold;">Data de Referência</div>
                        <select id="{c}-filtro-data" class="filter-select" onchange="document.getElementById('filtro-data').value = this.value; filtrarDados();" style="border: 1px solid #065F46;">
                            <option value="TODAS">Todas as Datas</option>
                            {opcoes_datas_html}
                        </select>
                    </div>
                </div>
            </div>
            <div class="sub-col" style="flex: 1.8;">
                <div class="chart-box" style="max-height: 200px;"><div class="section-title">Ranking por UBS</div><div id="{c}-ranking-ubs" style="display:flex; flex-direction:column; gap:6px;"></div></div>
                <div class="chart-box" style="max-height: 200px;"><div class="section-title">Ranking por Equipe</div><div id="{c}-ranking-equipe" style="display:flex; flex-direction:column; gap:6px;"></div></div>
            </div>
        </div>
    </div>
    """

# 5. Geração do HTML Interativo Final (usando raw strings ou separação limpa para evitar erros de sintaxe)
html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Monitoramento - Desenvolvimento Infantil</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #F0FDF4; color: #1F2937; margin: 0; padding: 0; height: 100vh; overflow: hidden; }}
        .app-container {{ display: flex; height: 100vh; width: 100vw; }}
        
        .sidebar {{ width: 220px; background-color: #065F46; color: white; display: flex; flex-direction: column; padding: 12px; box-shadow: 2px 0 5px rgba(0,0,0,0.1); z-index: 10; overflow-y: auto; flex-shrink: 0; }}
        
        /* Botão GPMA APS Centralizado e Estilizado */
        .sidebar-logo-container {{ display: flex; justify-content: center; width: 100%; margin-bottom: 15px; }}
        .sidebar-logo {{ background: white; border-radius: 8px; padding: 8px 12px; cursor: pointer; display: flex; justify-content: center; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.2); transition: transform 0.2s, box-shadow 0.2s; width: 90%; max-width: 170px; text-decoration: none; }}
        .sidebar-logo:hover {{ transform: scale(1.03); box-shadow: 0 4px 8px rgba(0,0,0,0.3); }}
        .sidebar-logo img {{ max-width: 100%; height: 40px; object-fit: contain; }}

        .sidebar-title {{ font-size: 13px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.2); padding-bottom: 5px; }}
        .filter-group {{ margin-bottom: 10px; }}
        .filter-label {{ font-size: 10px; text-transform: uppercase; font-weight: bold; margin-bottom: 3px; opacity: 0.9; }}
        .filter-select {{ width: 100%; padding: 5px; border-radius: 4px; border: none; font-size: 11px; background: white; color: #1F2937; }}
        
        .nav-section-title {{ font-size: 11px; font-weight: bold; text-transform: uppercase; margin: 10px 0 5px 0; border-bottom: 1px solid rgba(255,255,255,0.2); padding-bottom: 3px; }}
        .nav-menu {{ display: flex; flex-direction: column; gap: 6px; }}
        .nav-item {{ background-color: rgba(255,255,255,0.1); padding: 8px; border-radius: 4px; font-size: 10px; font-weight: bold; text-transform: uppercase; cursor: pointer; display: flex; align-items: center; gap: 8px; text-decoration: none; color: white; border: none; width: 100%; text-align: left; }}
        .nav-item:hover, .nav-item.active {{ background-color: #34D399; color: #065F46; }}
        .nav-item svg {{ width: 16px; height: 16px; fill: currentColor; flex-shrink: 0; }}
        
        .btn-limpar {{ margin-top: 10px; background-color: #10B981; color: white; border: 1px solid white; padding: 6px; border-radius: 4px; font-size: 11px; font-weight: bold; cursor: pointer; text-transform: uppercase; text-align: center; }}
        .btn-limpar:hover {{ background-color: #34D399; color: #065F46; }}

        .main-content {{ flex: 1; background-color: #F8FAFC; padding: 12px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }}
        
        .header-container {{ background-color: #065F46; color: white; padding: 10px 15px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header-title {{ font-size: 15px; font-weight: bold; text-transform: uppercase; }}
        .header-subtitle {{ font-size: 10px; opacity: 0.9; margin-top: 2px; max-width: 600px; }}
        .top-buttons {{ display: flex; gap: 6px; }}
        .btn-pb {{ background-color: #10B981; color: white; border: 1px solid white; padding: 5px 10px; border-radius: 4px; font-size: 10px; font-weight: bold; cursor: pointer; text-transform: uppercase; }}
        .btn-pb:hover {{ background-color: #34D399; color: #065F46; }}

        .cards-container {{ display: flex; gap: 10px; }}
        .card {{ background: white; border-radius: 6px; padding: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1; text-align: center; border-top: 4px solid #065F46; }}
        .card-title {{ font-size: 9px; color: #4B5563; text-transform: uppercase; font-weight: bold; }}
        .card-value {{ font-size: 18px; font-weight: bold; color: #065F46; margin-top: 2px; }}

        .main-grid {{ display: flex; gap: 10px; flex: 1; }}
        .box-left {{ background: white; border-radius: 6px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1.2; display: flex; flex-direction: column; gap: 10px; }}
        .box-right {{ background: white; border-radius: 6px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1.8; overflow-y: auto; max-height: 440px; }}
        .section-title {{ font-size: 11px; color: #065F46; font-weight: bold; text-transform: uppercase; margin-bottom: 8px; border-bottom: 2px solid #E5E7EB; padding-bottom: 4px; }}
        
        .metric-row {{ display: flex; align-items: center; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #E5E7EB; font-size: 11px; cursor: pointer; }}
        .metric-row:hover {{ background-color: #ECFDF5; }}
        .metric-left {{ display: flex; align-items: center; gap: 10px; max-width: 75%; }}
        .metric-icon {{ width: 22px; height: 22px; fill: #065F46; flex-shrink: 0; }}
        .metric-label {{ color: #1F2937; line-height: 1.2; }}
        .metric-val {{ font-weight: bold; color: #065F46; font-size: 13px; }}

        .page-view {{ display: none; flex-direction: column; gap: 10px; flex: 1; }}
        .page-view.active {{ display: flex; }}
        .sub-grid {{ display: flex; gap: 10px; flex: 1; }}
        .sub-col {{ display: flex; flex-direction: column; gap: 10px; flex: 1; }}
        .chart-box {{ background: white; border-radius: 6px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1; overflow-y: auto; max-height: 230px; }}
        .chart-box-large {{ background: white; border-radius: 6px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1; display: flex; flex-direction: column; height: 420px; }}
        .canvas-holder {{ position: relative; width: 100%; height: 240px; }}
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
                <button id="nav-a" class="nav-item" onclick="mudarPagina('a')"><svg viewBox="0 0 24 24"><path d="M19,3H5C3.89,3 3,3.89 3,5V19C3,20.1 3.89,21 5,21H19C20.1,21 21,20.1 21,19V5C21,3.89 20.1,3 19,3M19,5V19H5V5H19M11,7H13V9H11V7M11,11H13V17H11V11Z"/></svg>1ª Consulta Até 30 Dias</button>
                <button id="nav-b" class="nav-item" onclick="mudarPagina('b')"><svg viewBox="0 0 24 24"><path d="M19,4H18V2H16V4H8V2H6V4H5C3.89,4 3,4.89 3,6V20C3,21.1 3.89,22 5,22H19C20.1,22 21,21.1 21,20V6C21,4.89 20.1,4 19,4M19,20H5V10H19V20M19,8H5V6H19V8Z"/></svg>09 Consultas até 2 Anos</button>
                <button id="nav-c" class="nav-item" onclick="mudarPagina('c')"><svg viewBox="0 0 24 24"><path d="M19 3H5C3.9 3 3 3.9 3 5V19C3 20.1 3.9 21 5 21H19C20.1 21 21 20.1 21 19V5C21 3.9 20.1 3 19 3M12 6C13.66 6 15 7.34 15 9C15 10.66 13.66 12 12 12C10.34 12 9 10.66 9 9C9 7.34 10.34 6 12 6M16 16H8V15C8 13.67 10.67 13 12 13C13.33 13 16 13.67 16 15V16Z"/></svg>09 Registros Peso/Altura</button>
                <button id="nav-d" class="nav-item" onclick="mudarPagina('d')"><svg viewBox="0 0 24 24"><path d="M10 20V14H14V20H19V12H22L12 3L2 12H5V20H10Z"/></svg>Visitas Domiciliares ACS</button>
                <button id="nav-e" class="nav-item" onclick="mudarPagina('e')"><svg viewBox="0 0 24 24"><path d="M17.71,3.15L18.42,3.86C19.2,4.64 19.2,5.91 18.42,6.69L17.58,7.53L16.47,6.42L17.31,5.58C17.65,5.24 17.65,4.71 17.31,4.37L16.9,3.96C16.56,3.62 16.03,3.62 15.69,3.96L14.85,4.8L13.74,3.69L14.58,2.85C15.36,2.07 16.63,2.07 17.41,2.85L17.71,3.15M12.33,5.17L3,14.5V19H7.5L16.83,9.67L12.33,5.17Z"/></svg>Vacinas Recomendadas</button>
            </div>

            <div class="btn-limpar" onclick="limparFiltros()">Limpar Filtros</div>
        </div>

        <!-- CONTEÚDO PRINCIPAL -->
        <div class="main-content">

            <!-- PÁGINA 1: VISÃO GERAL -->
            <div id="view-geral" class="page-view active">
                <div class="header-container">
                    <div>
                        <div class="header-title">Monitoramento — Cuidado no Desenvolvimento Infantil</div>
                        <div class="header-subtitle">Avaliação do acompanhamento integral à saúde da criança na APS com pontuação oficial (Nota Metodológica C2: 20 pts por boa prática, total de 100 pts).</div>
                    </div>
                </div>

                <div class="cards-container">
                    <div class="card">
                        <div class="card-title">Total de Crianças</div>
                        <div id="val-total" class="card-value">0</div>
                    </div>
                    <div class="card">
                        <div class="card-title">Média Geral de Pontuação</div>
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
                        <div class="section-title">Ranking Média de Pontuação por UBS</div>
                        <div id="ranking-container" style="overflow-y: auto; max-height: 290px; flex: 1; display: flex; flex-direction: column; gap: 8px;"></div>
                        
                        <div style="border-top: 2px solid #E5E7EB; padding-top: 8px;">
                            <div class="filter-label" style="color: #065F46; font-weight: bold;">Data de Referência</div>
                            <select id="filtro-data" class="filter-select" onchange="filtrarDados();" style="border: 1px solid #065F46;">
                                <option value="TODAS">Todas as Datas</option>
                                {opcoes_datas_html}
                            </select>
                        </div>
                    </div>

                    <div class="box-right">
                        <div class="section-title">% de Não Cumprimento por Critério (Nota C2)</div>
                        
                        <div class="metric-row" onclick="mudarPagina('a')">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M19,3H5C3.89,3 3,3.89 3,5V19C3,20.1 3.89,21 5,21H19C20.1,21 21,20.1 21,19V5C21,3.89 20.1,3 19,3M19,5V19H5V5H19M11,7H13V9H11V7M11,11H13V17H11V11Z"/></svg>
                                <div class="metric-label"><b>(A)</b> 1ª consulta presencial realizada por médica(o) ou enfermeira(o), até o 30º dia de vida. (20 pts)</div>
                            </div>
                            <div id="nao-a" class="metric-val">0.00%</div>
                        </div>

                        <div class="metric-row" onclick="mudarPagina('b')">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M19,4H18V2H16V4H8V2H6V4H5C3.89,4 3,4.89 3,6V20C3,21.1 3.89,22 5,22H19C20.1,22 21,21.1 21,20V6C21,4.89 20.1,4 19,4M19,20H5V10H19V20M19,8H5V6H19V8Z"/></svg>
                                <div class="metric-label"><b>(B)</b> Pelo menos 09 consultas presenciais ou remotas realizadas até dois anos de vida. (20 pts)</div>
                            </div>
                            <div id="nao-b" class="metric-val">0.00%</div>
                        </div>

                        <div class="metric-row" onclick="mudarPagina('c')">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M19 3H5C3.9 3 3 3.9 3 5V19C3 20.1 3.9 21 5 21H19C20.1 21 21 20.1 21 19V5C21 3.9 20.1 3 19 3M12 6C13.66 6 15 7.34 15 9C15 10.66 13.66 12 12 12C10.34 12 9 10.66 9 9C9 7.34 10.34 6 12 6M16 16H8V15C8 13.67 10.67 13 12 13C13.33 13 16 13.67 16 15V16Z"/></svg>
                                <div class="metric-label"><b>(C)</b> Pelo menos 09 registros simultâneos de peso e altura até os dois anos de vida. (20 pts)</div>
                            </div>
                            <div id="nao-c" class="metric-val">0.00%</div>
                        </div>

                        <div class="metric-row" onclick="mudarPagina('d')">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M10 20V14H14V20H19V12H22L12 3L2 12H5V20H10Z"/></svg>
                                <div class="metric-label"><b>(D)</b> Pelo menos 02 visitas domiciliares por ACS/TACS (1ª até 30 dias e 2ª até 6 meses). (20 pts)</div>
                            </div>
                            <div id="nao-d" class="metric-val">0.00%</div>
                        </div>

                        <div class="metric-row" onclick="mudarPagina('e')" style="border-bottom: none;">
                            <div class="metric-left">
                                <svg class="metric-icon" viewBox="0 0 24 24"><path d="M17.71,3.15L18.42,3.86C19.2,4.64 19.2,5.91 18.42,6.69L17.58,7.53L16.47,6.42L17.31,5.58C17.65,5.24 17.65,4.71 17.31,4.37L16.9,3.96C16.56,3.62 16.03,3.62 15.69,3.96L14.85,4.8L13.74,3.69L14.58,2.85C15.36,2.07 16.63,2.07 17.41,2.85L17.71,3.15M12.33,5.17L3,14.5V19H7.5L16.83,9.67L12.33,5.17Z"/></svg>
                                <div class="metric-label"><b>(E)</b> Vacinas essenciais completas conforme o calendário infantil recomendado. (20 pts)</div>
                            </div>
                            <div id="nao-e" class="metric-val">0.00%</div>
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
            
            ['a', 'b', 'c', 'd', 'e'].forEach(k => {{
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
                ['a', 'b', 'c', 'd', 'e'].forEach(k => {{
                    const el = document.getElementById('nao-' + k);
                    if(el) el.textContent = '0.00%';
                }});
                gerarRankingUBS();
                return;
            }}

            const somaTotalPontos = dadosFiltrados.reduce((acc, d) => acc + d.Pontuação_Total, 0);
            const mediaGeral = somaTotalPontos / (total * 100) * 100;
            document.getElementById('val-media-praticas').textContent = mediaGeral.toFixed(2) + '%';

            const somaA = dadosFiltrados.reduce((acc, d) => acc + d.Pontuação_A, 0);
            const somaB = dadosFiltrados.reduce((acc, d) => acc + d.Pontuação_B, 0);
            const somaC = dadosFiltrados.reduce((acc, d) => acc + d.Pontuação_C, 0);
            const somaD = dadosFiltrados.reduce((acc, d) => acc + d.Pontuação_D, 0);
            const somaE = dadosFiltrados.reduce((acc, d) => acc + d.Pontuação_E, 0);

            document.getElementById('nao-a').textContent = (100 - (somaA / (total * 20)) * 100).toFixed(2) + '%';
            document.getElementById('nao-b').textContent = (100 - (somaB / (total * 20)) * 100).toFixed(2) + '%';
            document.getElementById('nao-c').textContent = (100 - (somaC / (total * 20)) * 100).toFixed(2) + '%';
            document.getElementById('nao-d').textContent = (100 - (somaD / (total * 20)) * 100).toFixed(2) + '%';
            document.getElementById('nao-e').textContent = (100 - (somaE / (total * 20)) * 100).toFixed(2) + '%';

            gerarRankingUBS();

            if (activeView !== 'geral') {{
                atualizarAbaIndividual(activeView, total);
            }}
        }}

        function atualizarAbaIndividual(criterio, total) {{
            const keyMap = {{ 'a': 'Pontuação_A', 'b': 'Pontuação_B', 'c': 'Pontuação_C', 'd': 'Pontuação_D', 'e': 'Pontuação_E' }};
            const col = keyMap[criterio];
            const somaCriterio = dadosFiltrados.reduce((acc, d) => acc + d[col], 0);
            
            const pctCumprimento = (somaCriterio / (total * 20)) * 100;
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
            
            const ubsMap = {{}};
            dadosFiltrados.forEach(d => {{
                if(!ubsMap[d.UBS]) ubsMap[d.UBS] = {{ soma: 0, count: 0 }};
                ubsMap[d.UBS].soma += d.Pontuação_Total;
                ubsMap[d.UBS].count += 1;
            }});

            const ranking = Object.keys(ubsMap).map(ubs => {{
                const media = (ubsMap[ubs].soma / (ubsMap[ubs].count * 100)) * 100;
                return {{ ubs, media }};
            }}).sort((a, b) => b.media - a.media);

            ranking.forEach((r, idx) => {{
                const row = document.createElement('div');
                row.style.cssText = 'display: flex; flex-direction: column; gap: 2px; font-size: 11px;';
                row.innerHTML = `
                    <div style="display: flex; justify-content: space-between; font-weight: bold; color: #1F2937;">
                        <span>${{idx + 1}}. ${{r.ubs}}</span>
                        <span style="color: #065F46;">${{r.media.toFixed(2)}}%</span>
                    </div>
                    <div style="background: #E5E7EB; border-radius: 4px; height: 6px; width: 100%; overflow: hidden;">
                        <div style="background: #10B981; height: 100%; width: ${{r.media}}%; border-radius: 4px;"></div>
                    </div>
                `;
                container.appendChild(row);
            }});
        }}

        function gerarRankingIndividual(criterio) {{
            const keyMap = {{ 'a': 'Pontuação_A', 'b': 'Pontuação_B', 'c': 'Pontuação_C', 'd': 'Pontuação_D', 'e': 'Pontuação_E' }};
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
                    const media = (mapUbs[ubs].soma / (mapUbs[ubs].count * 20)) * 100;
                    return {{ ubs, media }};
                }}).sort((a, b) => b.media - a.media);

                rankUbs.slice(0, 5).forEach((r, idx) => {{
                    const row = document.createElement('div');
                    row.style.cssText = 'display: flex; flex-direction: column; gap: 2px; font-size: 10px;';
                    row.innerHTML = `
                        <div style="display: flex; justify-content: space-between; font-weight: bold;">
                            <span>${{idx + 1}}. ${{r.ubs}}</span>
                            <span style="color: #065F46;">${{r.media.toFixed(2)}}%</span>
                        </div>
                        <div style="background: #E5E7EB; border-radius: 3px; height: 5px; width: 100%; overflow: hidden;">
                            <div style="background: #10B981; height: 100%; width: ${{r.media}}%; border-radius: 3px;"></div>
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
                    const media = (mapEq[equipe].soma / (mapEq[equipe].count * 20)) * 100;
                    return {{ equipe, media }};
                }}).sort((a, b) => b.media - a.media);

                rankEq.slice(0, 5).forEach((r, idx) => {{
                    const row = document.createElement('div');
                    row.style.cssText = 'display: flex; flex-direction: column; gap: 2px; font-size: 10px;';
                    row.innerHTML = `
                        <div style="display: flex; justify-content: space-between; font-weight: bold;">
                            <span>${{idx + 1}}. ${{r.equipe}}</span>
                            <span style="color: #065F46;">${{r.media.toFixed(2)}}%</span>
                        </div>
                        <div style="background: #E5E7EB; border-radius: 3px; height: 5px; width: 100%; overflow: hidden;">
                            <div style="background: #10B981; height: 100%; width: ${{r.media}}%; border-radius: 3px;"></div>
                        </div>
                    `;
                    containerEq.appendChild(row);
                }});
            }}
        }}

        function gerarGraficoLinhas(criterio) {{
            const keyMap = {{ 'a': 'Pontuação_A', 'b': 'Pontuação_B', 'c': 'Pontuação_C', 'd': 'Pontuação_D', 'e': 'Pontuação_E' }};
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
            const valores = labels.map(dt => (mapData[dt].soma / (mapData[dt].count * 20)) * 100);

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
                        borderColor: '#10B981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
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

print(f"Relatório gerado com sucesso em: {caminho_saida}")