import base64
from datetime import datetime
import glob
import os
import numpy as np
import pandas as pd

# =========================================================
# 1. DEFINIR CAMINHOS E DIRETÓRIO PARA CUIDADO DA MULHER (C7) - TEMA ROXO
# =========================================================
pasta_trabalho = r"W:\GPMA\NCAIS\Residência\Letícia Stefany Costa\Relatorio indicadores de saúde\Mulher\arquivos csv"
caminho_saida = r"W:\GPMA\NCAIS\Residência\Letícia Stefany Costa\Relatorio indicadores de saúde\Mulher\Relatorio_PowerBI_Mulher_Cancer.html"

if not os.path.exists(pasta_trabalho):
  os.makedirs(pasta_trabalho, exist_ok=True)

arquivos_csv = glob.glob(os.path.join(pasta_trabalho, "*.csv"))

if not arquivos_csv:
  print(f"Erro: Nenhum ficheiro CSV encontrado em: {pasta_trabalho}")
  exit()

print(f"=== A LER E UNIFICAR OS {len(arquivos_csv)} FICHEIROS DE CUIDADO DA MULHER ===")


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
        arquivo, sep=";", encoding="iso-8859-1", low_memory=False, dtype=str
    )
    temp_df.columns = (
        temp_df.columns.str.replace("ï»¿", "").str.replace('"', "").str.strip()
    )
    temp_df = temp_df.loc[
        :, ~temp_df.columns.str.contains(r"^Unnamed|\.\.\.", na=False)
    ]

    if not temp_df.empty:
      lista_dfs.append(temp_df)
  except Exception as e:
    print(f"  -> [ERRO] Falha ao ler {nome_arq}: {e}")

if not lista_dfs:
  print("Erro crítico: Nenhum dado válido foi carregado.")
  exit()

df = pd.concat(lista_dfs, ignore_index=True)
df = df.loc[:, ~df.columns.duplicated()]

# 2. Harmonização e Tratamento de Datas
col_data = None
for c in df.columns:
  if "DATA" in c.upper():
    col_data = c
    break

if col_data:
  df["DATA"] = limpar_e_converter_data(df[col_data])
else:
  df["DATA"] = pd.to_datetime("today")

df["DATA_STR"] = df["DATA"].dt.strftime("%Y-%m-%d").fillna(
    datetime.today().strftime("%Y-%m-%d")
)

# 3. MAPEAMENTO DAS COLUNAS DE PONTUAÇÃO (Pts_A até Pts_D)
mapeamento_pts = {
    "Pts_A": "Pontuação_A",
    "Pts_B": "Pontuação_B",
    "Pts_C": "Pontuação_C",
    "Pts_D": "Pontuação_D",
}

for k_orig, k_dest in mapeamento_pts.items():
  if k_orig in df.columns:
    df[k_dest] = pd.to_numeric(df[k_orig], errors="coerce").fillna(0)
  else:
    df[k_dest] = 0

if "Pontuacao_Total" in df.columns:
  df["Pontuação_Total"] = (
      pd.to_numeric(df["Pontuacao_Total"], errors="coerce").fillna(0)
  )
else:
  df["Pontuação_Total"] = sum([df[k] for k in mapeamento_pts.values()])

df["UBS"] = (
    df["UBS"].fillna("Não informada") if "UBS" in df.columns else "Não informada"
)
df["EQUIPE"] = (
    df["EQUIPE"].fillna("Não informada")
    if "EQUIPE" in df.columns
    else "Não informada"
)

colunas_necessarias = (
    ["DATA_STR", "UBS", "EQUIPE"]
    + list(mapeamento_pts.values())
    + ["Pontuação_Total"]
)
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
    else '<div style="font-weight:bold; color:#9333EA; font-size:12px;'
    ' text-align:center;">GPMA - APS</div>'
)

# ÍCONES EM EMOJI SEGUROS (Tema Roxo - Cuidado da Mulher)
svg_icones = {"a": "📋", "b": "💉", "c": "👩‍⚕️", "d": "🎗️"}

secoes_individuais = [
    (
        "a",
        "RASTREAMENTO CÂNCER DO COLO DO ÚTERO (A)",
        (
            "Ter pelo menos 01 exame de rastreamento (citopatológico ou teste"
            " HPV) nos últimos 36 a 60 meses para mulheres e homens transgênero"
            " de 25 a 64 anos. (Peso: 20 pts)"
        ),
        20,
    ),
    (
        "b",
        "VACINA CONTRA O HPV (B)",
        (
            "Ter pelo menos 01 dose da vacina HPV em crianças e adolescentes do"
            " sexo feminino de 09 a 14 anos. (Peso: 30 pts)"
        ),
        30,
    ),
    (
        "c",
        "SAÚDE SEXUAL E REPRODUTIVA (C)",
        (
            "Ter atendimento presencial ou remoto sobre saúde sexual e"
            " reprodutiva nos últimos 12 meses para pessoas de 14 a 69 anos."
            " (Peso: 30 pts)"
        ),
        30,
    ),
    (
        "d",
        "RASTREAMENTO CÂNCER DE MAMA (D)",
        (
            "Ter pelo menos 01 exame de mamografia solicitado ou avaliado nos"
            " últimos 24 meses para mulheres e homens transgênero de 50 a 69"
            " anos. (Peso: 20 pts)"
        ),
        20,
    ),
]

html_secoes_abafas = ""
for c, titulo, sub, peso in secoes_individuais:
  html_secoes_abafas += f"""
    <div id="view-{c}" class="page-view">
        <div class="header-container" style="background-color: #9333EA;">
            <div>
                <div class="header-title">Cuidado da Mulher: {titulo}</div>
                <div class="header-subtitle"><b>BOA PRÁTICA:</b> {sub}</div>
            </div>
            <div class="top-buttons"><button class="btn-pb" onclick="mudarPagina('geral')" style="background-color: #A855F7; border-color: white;">Voltar</button></div>
        </div>
        <div class="cards-container">
            <div class="card" style="border-top-color: #9333EA;"><div class="card-title">Cumprimento (Média Ponderada)</div><div id="{c}-val-cumprimento" class="card-value" style="color: #9333EA;">0.00%</div></div>
            <div class="card" style="border-top-color: #9333EA;"><div class="card-title">Não Atendido</div><div id="{c}-val-naopreenchido" class="card-value" style="color: #9333EA;">0.00%</div></div>
        </div>
        <div class="sub-grid">
            <div class="sub-col" style="flex: 1.2;">
                <div class="chart-box-large">
                    <div class="section-title" style="color: #9333EA; border-bottom-color: #F3E8FF;">Evolução ao Longo do Tempo</div>
                    <div class="canvas-holder"><canvas id="{c}-canvas-linhas"></canvas></div>
                    <div style="border-top: 2px solid #F3E8FF; padding-top: 8px; margin-top: auto;">
                        <div class="filter-label" style="color: #9333EA; font-weight: bold;">Data de Referência</div>
                        <select id="{c}-filtro-data" class="filter-select" onchange="document.getElementById('filtro-data').value = this.value; filtrarDados();" style="border: 1px solid #9333EA;">
                            <option value="TODAS">Todas as Datas</option>
                            {opcoes_datas_html}
                        </select>
                    </div>
                </div>
            </div>
            <div class="sub-col" style="flex: 1.8;">
                <div class="chart-box" style="max-height: 200px;"><div class="section-title" style="color: #9333EA; border-bottom-color: #F3E8FF;">Ranking por UBS</div><div id="{c}-ranking-ubs" style="display:flex; flex-direction:column; gap:6px;"></div></div>
                <div class="chart-box" style="max-height: 200px;"><div class="section-title" style="color: #9333EA; border-bottom-color: #F3E8FF;">Ranking por Equipe</div><div id="{c}-ranking-equipe" style="display:flex; flex-direction:column; gap:6px;"></div></div>
            </div>
        </div>
    </div>
    """

# 5. Geração do HTML Interativo Final (Tema Roxo - Cuidado da Mulher)
html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Monitoramento - Cuidado da Mulher na Prevenção do Câncer</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #FAF5FF; color: #1F2937; margin: 0; padding: 0; height: 100vh; overflow: hidden; }}
        .app-container {{ display: flex; height: 100vh; width: 100vw; }}
        
        .sidebar {{ width: 235px; background-color: #9333EA; color: white; display: flex; flex-direction: column; padding: 12px; box-shadow: 2px 0 5px rgba(0,0,0,0.1); z-index: 10; overflow-y: auto; flex-shrink: 0; }}
        
        .sidebar-logo-container {{ display: flex; justify-content: center; width: 100%; margin-bottom: 15px; }}
        .sidebar-logo {{ background: white; border-radius: 8px; padding: 8px 12px; cursor: pointer; display: flex; justify-content: center; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.2); transition: transform 0.2s, box-shadow 0.2s; width: 90%; max-width: 170px; text-decoration: none; }}
        .sidebar-logo:hover {{ transform: scale(1.03); box-shadow: 0 4px 8px rgba(0,0,0,0.3); }}
        .sidebar-logo img {{ max-width: 100%; height: 40px; object-fit: contain; }}

        .sidebar-title {{ font-size: 13px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; border-bottom: 1px solid rgba(255,255,255,0.2); padding-bottom: 5px; }}
        .filter-group {{ margin-bottom: 10px; }}
        .filter-label {{ font-size: 10px; text-transform: uppercase; font-weight: bold; margin-bottom: 3px; opacity: 0.9; }}
        .filter-select {{ width: 100%; padding: 5px; border-radius: 4px; border: none; font-size: 11px; background: white; color: #1F2937; }}
        
        .nav-section-title {{ font-size: 11px; font-weight: bold; text-transform: uppercase; margin: 10px 0 5px 0; border-bottom: 1px solid rgba(255,255,255,0.2); padding-bottom: 3px; }}
        .nav-menu {{ display: flex; flex-direction: column; gap: 5px; }}
        .nav-item {{ background-color: rgba(255,255,255,0.1); padding: 7px; border-radius: 4px; font-size: 9.5px; font-weight: bold; text-transform: uppercase; cursor: pointer; display: flex; align-items: center; gap: 8px; text-decoration: none; color: white; border: none; width: 100%; text-align: left; }}
        .nav-item:hover, .nav-item.active {{ background-color: #A855F7; color: #3B0764; }}
        
        .btn-limpar {{ margin-top: 10px; background-color: #7E22CE; color: white; border: 1px solid white; padding: 6px; border-radius: 4px; font-size: 11px; font-weight: bold; cursor: pointer; text-transform: uppercase; text-align: center; }}
        .btn-limpar:hover {{ background-color: #9333EA; color: white; }}

        .main-content {{ flex: 1; background-color: #F3E8FF; padding: 12px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }}
        
        .header-container {{ background-color: #9333EA; color: white; padding: 10px 15px; border-radius: 6px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header-title {{ font-size: 15px; font-weight: bold; text-transform: uppercase; }}
        .header-subtitle {{ font-size: 10px; opacity: 0.9; margin-top: 2px; max-width: 650px; }}
        .top-buttons {{ display: flex; gap: 6px; }}
        .btn-pb {{ background-color: #7E22CE; color: white; border: 1px solid white; padding: 5px 10px; border-radius: 4px; font-size: 10px; font-weight: bold; cursor: pointer; text-transform: uppercase; }}
        .btn-pb:hover {{ background-color: #9333EA; color: white; }}

        .cards-container {{ display: flex; gap: 10px; }}
        .card {{ background: white; border-radius: 6px; padding: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1; text-align: center; border-top: 4px solid #9333EA; }}
        .card-title {{ font-size: 9px; color: #4B5563; text-transform: uppercase; font-weight: bold; }}
        .card-value {{ font-size: 18px; font-weight: bold; color: #9333EA; margin-top: 2px; }}

        .main-grid {{ display: flex; gap: 10px; flex: 1; }}
        .box-left {{ background: white; border-radius: 6px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1.2; display: flex; flex-direction: column; gap: 10px; }}
        .box-right {{ background: white; border-radius: 6px; padding: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); flex: 1.8; overflow-y: auto; max-height: 440px; }}
        .section-title {{ font-size: 11px; color: #9333EA; font-weight: bold; text-transform: uppercase; margin-bottom: 8px; border-bottom: 2px solid #F3E8FF; padding-bottom: 4px; }}
        
        .metric-row {{ display: flex; align-items: center; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #F3E8FF; font-size: 10.5px; cursor: pointer; }}
        .metric-row:hover {{ background-color: #FAF5FF; }}
        .metric-left {{ display: flex; align-items: center; gap: 8px; max-width: 80%; }}
        .metric-label {{ color: #1F2937; line-height: 1.15; }}
        .metric-val {{ font-weight: bold; color: #9333EA; font-size: 12px; }}

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

            <div class="nav-section-title">Boas Práticas (Nota C7)</div>
            <div class="nav-menu">
                <button id="nav-a" class="nav-item" onclick="mudarPagina('a')">{svg_icones["a"]} (A) Rastreamento Colo Uterino</button>
                <button id="nav-b" class="nav-item" onclick="mudarPagina('b')">{svg_icones["b"]} (B) Vacina HPV (09-14 anos)</button>
                <button id="nav-c" class="nav-item" onclick="mudarPagina('c')">{svg_icones["c"]} (C) Saúde Sexual e Reprodutiva</button>
                <button id="nav-d" class="nav-item" onclick="mudarPagina('d')">{svg_icones["d"]} (D) Rastreamento Câncer Mama</button>
            </div>

            <div class="btn-limpar" onclick="limparFiltros()">Limpar Filtros</div>
        </div>

        <!-- CONTEÚDO PRINCIPAL -->
        <div class="main-content">

            <!-- PÁGINA 1: VISÃO GERAL -->
            <div id="view-geral" class="page-view active">
                <div class="header-container">
                    <div>
                        <div class="header-title">Monitoramento — Cuidado da Mulher na Prevenção do Câncer</div>
                        <div class="header-subtitle">Avaliação do acesso e acompanhamento efetivo da saúde da mulher e homem transgênero na APS (Nota C7: 4 boas práticas, total de 100 pontos).</div>
                    </div>
                </div>

                <div class="cards-container">
                    <div class="card">
                        <div class="card-title">Total de Mulheres/Pessoas</div>
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
                        
                        <div style="border-top: 2px solid #F3E8FF; padding-top: 8px;">
                            <div class="filter-label" style="color: #9333EA; font-weight: bold;">Data de Referência</div>
                            <select id="filtro-data" class="filter-select" onchange="filtrarDados();" style="border: 1px solid #9333EA;">
                                <option value="TODAS">Todas as Datas</option>
                                {opcoes_datas_html}
                            </select>
                        </div>
                    </div>

                    <div class="box-right">
                        <div class="section-title">% de Não Cumprimento por Critério (Nota C7)</div>
                        
                        <div class="metric-row" onclick="mudarPagina('a')"><div class="metric-left">{svg_icones["a"]}<div class="metric-label"><b>(A)</b> Rastreamento câncer do colo do útero (20 pts)</div></div><div id="nao-a" class="metric-val">0.00%</div></div>
                        <div class="metric-row" onclick="mudarPagina('b')"><div class="metric-left">{svg_icones["b"]}<div class="metric-label"><b>(B)</b> Vacina contra o HPV (09 a 14 anos) (30 pts)</div></div><div id="nao-b" class="metric-val">0.00%</div></div>
                        <div class="metric-row" onclick="mudarPagina('c')"><div class="metric-left">{svg_icones["c"]}<div class="metric-label"><b>(C)</b> Atendimento de saúde sexual e reprodutiva (30 pts)</div></div><div id="nao-c" class="metric-val">0.00%</div></div>
                        <div class="metric-row" onclick="mudarPagina('d')" style="border-bottom: none;"><div class="metric-left">{svg_icones["d"]}<div class="metric-label"><b>(D)</b> Rastreamento câncer de mama (50-69 anos) (20 pts)</div></div><div id="nao-d" class="metric-val">0.00%</div></div>
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
        const pesosCriterios = {{ 'a': 20, 'b': 30, 'c': 30, 'd': 20 }};

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
            
            ['a', 'b', 'c', 'd'].forEach(k => {{
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
                ['a', 'b', 'c', 'd'].forEach(k => {{
                    const el = document.getElementById('nao-' + k);
                    if(el) el.textContent = '0.00%';
                }});
                gerarRankingUBS();
                return;
            }}

            const mapColunas = {{
                'a': 'Pontuação_A', 'b': 'Pontuação_B', 'c': 'Pontuação_C', 'd': 'Pontuação_D'
            }};

            let somaTotalPontosObtidos = 0;
            const somaMaxPossivel = total * 100;

            Object.keys(mapColunas).forEach(k => {{
                const col = mapColunas[k];
                const peso = pesosCriterios[k];
                const somaPontosCriterio = dadosFiltrados.reduce((acc, d) => acc + d[col], 0);
                somaTotalPontosObtidos += somaPontosCriterio;

                const naoAtendidoPct = 100 - ((somaPontosCriterio / (total * peso)) * 100);
                const elNao = document.getElementById('nao-' + k);
                if(elNao) elNao.textContent = Math.max(0, naoAtendidoPct).toFixed(2) + '%';
            }});

            const mediaGeral = (somaTotalPontosObtidos / somaMaxPossivel) * 100;
            document.getElementById('val-media-praticas').textContent = mediaGeral.toFixed(2) + '%';

            gerarRankingUBS();

            if (activeView !== 'geral') {{
                atualizarAbaIndividual(activeView, total);
            }}
        }}

        function atualizarAbaIndividual(criterio, total) {{
            const colMap = {{
                'a': 'Pontuação_A', 'b': 'Pontuação_B', 'c': 'Pontuação_C', 'd': 'Pontuação_D'
            }};
            const col = colMap[criterio];
            const peso = pesosCriterios[criterio];

            const somaCriterio = dadosFiltrados.reduce((acc, d) => acc + d[col], 0);
            const maxCriterio = total * peso;

            const pctCumprimento = maxCriterio > 0 ? (somaCriterio / maxCriterio) * 100 : 0;
            const pctNaoAtendido = 100 - pctCumprimento;

            document.getElementById(criterio + '-val-cumprimento').textContent = pctCumprimento.toFixed(2) + '%';
            document.getElementById(criterio + '-val-naopreenchido').textContent = Math.max(0, pctNaoAtendido).toFixed(2) + '%';

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
                const media = ubsMap[ubs].soma / ubsMap[ubs].count;
                return {{ ubs, media }};
            }}).sort((a, b) => b.media - a.media);

            ranking.forEach((r, idx) => {{
                const row = document.createElement('div');
                row.style.cssText = 'display: flex; flex-direction: column; gap: 2px; font-size: 11px; margin-bottom: 4px;';
                row.innerHTML = `
                    <div style="display: flex; justify-content: space-between; font-weight: bold; color: #1F2937;">
                        <span>${{idx + 1}}. ${{r.ubs}}</span>
                        <span style="color: #9333EA;">${{r.media.toFixed(2)}}%</span>
                    </div>
                    <div style="background: #F3E8FF; border-radius: 4px; height: 6px; width: 100%; overflow: hidden;">
                        <div style="background: #9333EA; height: 100%; width: ${{r.media}}%; border-radius: 4px;"></div>
                    </div>
                `;
                container.appendChild(row);
            }});
        }}

        function gerarRankingIndividual(criterio) {{
            const colMap = {{
                'a': 'Pontuação_A', 'b': 'Pontuação_B', 'c': 'Pontuação_C', 'd': 'Pontuação_D'
            }};
            const col = colMap[criterio];
            const peso = pesosCriterios[criterio];

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
                    const media = (mapUbs[ubs].soma / (mapUbs[ubs].count * peso)) * 100;
                    return {{ ubs, media }};
                }}).sort((a, b) => b.media - a.media);

                rankUbs.slice(0, 5).forEach((r, idx) => {{
                    const row = document.createElement('div');
                    row.style.cssText = 'display: flex; flex-direction: column; gap: 2px; font-size: 10px; margin-bottom: 4px;';
                    row.innerHTML = `
                        <div style="display: flex; justify-content: space-between; font-weight: bold;">
                            <span>${{idx + 1}}. ${{r.ubs}}</span>
                            <span style="color: #9333EA;">${{r.media.toFixed(2)}}%</span>
                        </div>
                        <div style="background: #F3E8FF; border-radius: 3px; height: 5px; width: 100%; overflow: hidden;">
                            <div style="background: #9333EA; height: 100%; width: ${{r.media}}%; border-radius: 3px;"></div>
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
                    const media = (mapEq[equipe].soma / (mapEq[equipe].count * peso)) * 100;
                    return {{ equipe, media }};
                }}).sort((a, b) => b.media - a.media);

                rankEq.slice(0, 5).forEach((r, idx) => {{
                    const row = document.createElement('div');
                    row.style.cssText = 'display: flex; flex-direction: column; gap: 2px; font-size: 10px; margin-bottom: 4px;';
                    row.innerHTML = `
                        <div style="display: flex; justify-content: space-between; font-weight: bold;">
                            <span>${{idx + 1}}. ${{r.equipe}}</span>
                            <span style="color: #9333EA;">${{r.media.toFixed(2)}}%</span>
                        </div>
                        <div style="background: #F3E8FF; border-radius: 3px; height: 5px; width: 100%; overflow: hidden;">
                            <div style="background: #9333EA; height: 100%; width: ${{r.media}}%; border-radius: 3px;"></div>
                        </div>
                    `;
                    containerEq.appendChild(row);
                }});
            }}
        }}

        function gerarGraficoLinhas(criterio) {{
            const colMap = {{
                'a': 'Pontuação_A', 'b': 'Pontuação_B', 'c': 'Pontuação_C', 'd': 'Pontuação_D'
            }};
            const col = colMap[criterio];
            const peso = pesosCriterios[criterio];
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
            const valores = labels.map(dt => (mapData[dt].soma / (mapData[dt].count * peso)) * 100);

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
                        borderColor: '#9333EA',
                        backgroundColor: 'rgba(147, 51, 234, 0.1)',
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

print(
    f"Relatório de Cuidado da Mulher gerado com sucesso em: {caminho_saida}"
)