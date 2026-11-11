# ==============================================================================
# MONITORAMENTO APS - CUIDADO NA GESTAÇÃO E PUERPÉRIO (NOTA METODOLÓGICA C3)
# ==============================================================================

library(tidyverse)
library(lubridate)
library(data.table)

# 1. Definir caminhos de entrada e saída
pasta_entrada <- "W:/GPMA/NCAIS/Residência/Letícia Stefany Costa/arquivos e-sus/salvar esusgestante/09 de novembro"
caminho_saida <- "W:/GPMA/NCAIS/Residência/Letícia Stefany Costa/Relatorio indicadores de saúde/Gestante/arquivos csv/9denovembro.csv"

# Garantir que o diretório de saída existe
dir.create(dirname(caminho_saida), recursive = TRUE, showWarnings = FALSE)

arquivos <- list.files(path = pasta_entrada, pattern = "\\.csv$", full.names = TRUE)

if (length(arquivos) == 0) {
  stop("Nenhum arquivo CSV encontrado na pasta de trabalho especificada!")
}

lista_dados_equipes <- list()

# ==============================================================================
# 2. LOOP PARA PROCESSAR ARQUIVO POR ARQUIVO
# ==============================================================================
for (arquivo in arquivos) {
  
  cat("Processando o arquivo:", basename(arquivo), "\n")
  
  # A. Capturar UBS (Linha 5)
  linhas_texto <- read_lines(arquivo, skip = 4, n_max = 1, locale = locale(encoding = "Latin1"))
  nome_ubs_limpo <- str_extract(linhas_texto, "UBS[^;]+") %>% str_trim()
  
  if (is.na(nome_ubs_limpo) || nome_ubs_limpo == "") {
    nome_ubs_limpo <- "UBS DESCONHECIDA" 
  }
  
  # B. Capturar Equipe (Linha 10)
  linha_10_texto <- read_lines(arquivo, skip = 9, n_max = 1, locale = locale(encoding = "Latin1"))
  conteudo_equipe <- str_split(linha_10_texto, ";")[[1]]
  
  if (length(conteudo_equipe) >= 2) {
    texto_equipe_completo <- conteudo_equipe[2]
    nome_equipe_limpo <- str_split(texto_equipe_completo, ",")[[1]][1] %>% str_trim()
  } else {
    nome_equipe_limpo <- "EQUIPE DESCONHECIDA"
  }
  
  if (is.na(nome_equipe_limpo) || nome_equipe_limpo == "") {
    nome_equipe_limpo <- "EQUIPE DESCONHECIDA"
  }
  
  # C. Diferenciar Equipes Gêmeas
  equipes_gemeas <- c("EQUIPE AMARELA", "EQUIPE AZUL", "EQUIPE LILAS", 
                      "EQUIPE VERDE", "EQUIPE VERMELHA")
  
  if (nome_equipe_limpo %in% equipes_gemeas) {
    if (str_detect(nome_ubs_limpo, "UBS 2 ASA NORTE")) {
      nome_equipe_limpo <- paste0(nome_equipe_limpo, "_AN")
    } else if (str_detect(nome_ubs_limpo, "UBS 1 ASA SUL")) {
      nome_equipe_limpo <- paste0(nome_equipe_limpo, "_AS")
    }
  }
  
  # D. Leitura dos dados da planilha (Pulo de 24 linhas padrão e-SUS)
  dados_brutos <- read_delim(
    file = arquivo,
    delim = ";", 
    skip = 24,
    locale = locale(encoding = "Latin1"),
    show_col_types = FALSE,
    trim_ws = TRUE,
    name_repair = "unique",
    col_types = cols(.default = col_character())
  )
  
  if (nrow(dados_brutos) == 0) {
    cat("⚠️ Atenção: O arquivo", basename(arquivo), "está sem dados cadastrados.\n")
    next
  }
  
  # E. Mapeamento correto das colunas reais do e-SUS para a Nota C3
  obter_coluna <- function(df, padrao) {
    col <- names(df)[str_detect(names(df), regex(padrao, ignore_case = TRUE))]
    if (length(col) > 0) return(col[1]) else return(NULL)
  }
  
  col_atend_12s <- obter_coluna(dados_brutos, "até 12 semanas no pré-natal")
  col_qtd_cons  <- obter_coluna(dados_brutos, "Quantidade de atendimentos no pré-natal")
  col_qtd_pa    <- obter_coluna(dados_brutos, "Quantidade de medições de pressão arterial")
  col_qtd_peso  <- obter_coluna(dados_brutos, "Quantidade de medições simultâneas de peso")
  col_vd_gest   <- obter_coluna(dados_brutos, "visitas domiciliares no pré-natal")
  col_dTpa      <- obter_coluna(dados_brutos, "dTpa")
  
  # Exames 1º Trimestre
  col_hiv_1t    <- obter_coluna(dados_brutos, "HIV.*primeiro trimestre")
  col_sif_1t    <- obter_coluna(dados_brutos, "Sífilis.*primeiro trimestre")
  col_hepb_1t   <- obter_coluna(dados_brutos, "Hepatite B.*primeiro trimestre")
  col_hepc_1t   <- obter_coluna(dados_brutos, "Hepatite C.*primeiro trimestre")
  
  # Exames 3º Trimestre
  col_hiv_3t    <- obter_coluna(dados_brutos, "HIV.*terceiro trimestre")
  col_sif_3t    <- obter_coluna(dados_brutos, "Sifilis.*terceiro trimestre")
  
  # Puerpério e Saúde Bucal
  col_cons_puer <- obter_coluna(dados_brutos, "Quantidade de atendimentos no puerpério")
  col_vd_puer   <- obter_coluna(dados_brutos, "visitas domiciliares no puerpério")
  col_odonto    <- obter_coluna(dados_brutos, "atendimentos odontológicos no pré-natal")
  
  # Funções auxiliares de avaliação blindadas
  avaliar_limite <- function(val, limite) {
    v <- suppressWarnings(as.numeric(val))
    if_else(is.na(v), 0, if_else(v >= limite, 1, 0))
  }
  
  avaliar_sim_ou_registro <- function(val) {
    v <- toupper(coalesce(val, ""))
    if_else(v == "SIM" | str_detect(v, "REF") | str_detect(v, "VACINA") | (str_detect(v, "^D -") & v != "-"), 1, 0)
  }
  
  dados_processados <- dados_brutos %>%
    # REMOÇÃO DE DADOS SENSÍVEIS
    select(
      -matches(
        "Nome|CPF|CNS|Telefone|Rua|Número|Complemento|Bairro|CEP|Data de nascimento|Titular.*Bolsa|Vigência",
        ignore.case = TRUE
      )
    ) %>%
    mutate(
      DATA = as.character(Sys.Date()),
      IDENTIFICAÇÃO = NA_character_,
      UBS = nome_ubs_limpo,        
      EQUIPE = nome_equipe_limpo,
      
      # Pontuação Individual das 11 Boas Práticas (Nota C3)
      Pts_A = if (!is.null(col_atend_12s)) avaliar_limite(.data[[col_atend_12s]], 1) * 10 else 0,
      Pts_B = if (!is.null(col_qtd_cons)) avaliar_limite(.data[[col_qtd_cons]], 7) * 9 else 0,
      Pts_C = if (!is.null(col_qtd_pa)) avaliar_limite(.data[[col_qtd_pa]], 7) * 9 else 0,
      Pts_D = if (!is.null(col_qtd_peso)) avaliar_limite(.data[[col_qtd_peso]], 7) * 9 else 0,
      Pts_E = if (!is.null(col_vd_gest)) avaliar_limite(.data[[col_vd_gest]], 3) * 9 else 0,
      Pts_F = if (!is.null(col_dTpa)) avaliar_sim_ou_registro(.data[[col_dTpa]]) * 9 else 0,
      
      Pts_G = if (!is.null(col_hiv_1t) && !is.null(col_sif_1t)) {
        if_else(avaliar_sim_ou_registro(.data[[col_hiv_1t]]) == 1 & avaliar_sim_ou_registro(.data[[col_sif_1t]]) == 1, 9, 0)
      } else { 0 },
      
      Pts_H = if (!is.null(col_hiv_3t) && !is.null(col_sif_3t)) {
        if_else(avaliar_sim_ou_registro(.data[[col_hiv_3t]]) == 1 & avaliar_sim_ou_registro(.data[[col_sif_3t]]) == 1, 9, 0)
      } else { 0 },
      
      Pts_I = if (!is.null(col_cons_puer)) avaliar_limite(.data[[col_cons_puer]], 1) * 9 else 0,
      Pts_J = if (!is.null(col_vd_puer)) avaliar_limite(.data[[col_vd_puer]], 1) * 9 else 0,
      Pts_K = if (!is.null(col_odonto)) avaliar_limite(.data[[col_odonto]], 1) * 9 else 0,
      
      # Pontuação Total (Max 100 pts)
      Pontuacao_Total = Pts_A + Pts_B + Pts_C + Pts_D + Pts_E + Pts_F + 
        Pts_G + Pts_H + Pts_I + Pts_J + Pts_K,
      
      Pct_Atingimento = as.character((Pontuacao_Total / 100) * 100)
    ) %>%
    relocate(DATA, IDENTIFICAÇÃO, UBS, EQUIPE, .before = everything())
  
  lista_dados_equipes[[arquivo]] <- dados_processados
}

# ==============================================================================
# 3. CONSOLIDAR TODAS AS EQUIPES E EXPORTAR
# ==============================================================================
if (length(lista_dados_equipes) > 0) {
  dados_finais_consolidados <- bind_rows(lista_dados_equipes)
  
  fwrite(
    dados_finais_consolidados,
    caminho_saida,
    sep = ";",
    bom = TRUE,
    na = ""
  )
  
  cat("\nProcessamento concluído com sucesso! Arquivo salvo em:\n", caminho_saida)
} else {
  cat("\n❌ Erro: Nenhum arquivo .csv válido foi processado.\n")
}