# ==============================================================================
# MONITORAMENTO APS - CUIDADO DA PESSOA IDOSA (NOTA METODOLÓGICA C6)
# ==============================================================================

library(tidyverse)
library(lubridate)
library(data.table)

# 1. Definir caminhos de entrada e saída
pasta_entrada <- "W:/GPMA/NCAIS/Residência/Letícia Stefany Costa/arquivos e-sus/pasta esusidoso/9 de novembro"
caminho_saida <- "W:/GPMA/NCAIS/Residência/Letícia Stefany Costa/Relatorio indicadores de saúde/pessoa idosa/arquivos csv/9denovembro.csv"

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
  
  # A. Capturar UBS (Linha 5 do arquivo / skip = 4)
  linhas_texto <- read_lines(arquivo, skip = 4, n_max = 1, locale = locale(encoding = "Latin1"))
  nome_ubs_limpo <- str_extract(linhas_texto, "UBS[^;]+") %>% str_trim()
  
  if (is.na(nome_ubs_limpo) || nome_ubs_limpo == "") {
    # Tenta capturar qualquer texto após "UNIDADE DE SAÚDE" caso não comece com UBS
    nome_ubs_limpo <- str_remove(linhas_texto, "UNIDADE DE SAÚDE[:]?") %>% str_split(";") %>% pluck(1, 1) %>% str_trim()
  }
  if (is.na(nome_ubs_limpo) || nome_ubs_limpo == "") {
    nome_ubs_limpo <- "UBS DESCONHECIDA" 
  }
  
  # B. Capturar Equipe (Linha 10 do arquivo / skip = 9)
  linha_10_texto <- read_lines(arquivo, skip = 9, n_max = 1, locale = locale(encoding = "Latin1"))
  conteudo_equipe <- str_split(linha_10_texto, ";")[[1]]
  
  if (length(conteudo_equipe) >= 2 && conteudo_equipe[2] != "") {
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
  
  # D. Leitura dos dados da tabela (Cabeçalho na linha 28 / skip = 27)
  dados_brutos <- read_delim(
    file = arquivo,
    delim = ";", 
    skip = 27,
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
  
  # E. Mapeamento dinâmico das colunas da Nota C6
  obter_coluna <- function(df, padrao) {
    col <- names(df)[str_detect(names(df), regex(padrao, ignore_case = TRUE))]
    if (length(col) > 0) return(col[1]) else return(NULL)
  }
  
  col_meses_med_enf <- obter_coluna(dados_brutos, "Meses desde o último atendimento.*(médico|enfermeiro)")
  col_dias_med      <- obter_coluna(dados_brutos, "Dias desde o último atendimento médico")
  col_dias_enf      <- obter_coluna(dados_brutos, "Dias desde o último atendimento de enfermagem")
  
  col_simultaneo    <- obter_coluna(dados_brutos, "Registros de peso e altura simultâneos")
  col_qtd_vd        <- obter_coluna(dados_brutos, "Quantidade de visitas domiciliares")
  col_influenza     <- obter_coluna(dados_brutos, "Influenza.*últimos 12 meses")
  
  # Funções auxiliares de avaliação para C6 (25 pontos cada boa prática)
  avaliar_recente_meses <- function(val, max_meses = 12) {
    v <- suppressWarnings(as.numeric(val))
    if_else(is.na(v), 0, if_else(v <= max_meses, 1, 0))
  }
  
  avaliar_recente_dias <- function(val, max_dias = 365) {
    v <- suppressWarnings(as.numeric(val))
    if_else(is.na(v), 0, if_else(v <= max_dias, 1, 0))
  }
  
  avaliar_simultaneo_b <- function(val) {
    v <- suppressWarnings(as.numeric(val))
    if_else(is.na(v), 0, if_else(v >= 1, 1, 0))
  }
  
  avaliar_visitas_c <- function(val) {
    v <- suppressWarnings(as.numeric(val))
    if_else(is.na(v), 0, if_else(v >= 2, 1, 0))
  }
  
  avaliar_vacina_d <- function(val) {
    v <- toupper(coalesce(val, ""))
    if_else(v != "" & v != "SEM REGISTRO" & v != "-" & str_detect(v, "INFLUENZA|INF|33|77"), 1, 0)
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
      
      # Pontuação Individual (Nota C6 - 25 pontos cada)
      Pts_A = if (!is.null(col_dias_med) && !is.null(col_dias_enf)) {
        if_else(avaliar_recente_dias(.data[[col_dias_med]], 365) == 1 | avaliar_recente_dias(.data[[col_dias_enf]], 365) == 1, 1, 0) * 25
      } else if (!is.null(col_meses_med_enf)) {
        avaliar_recente_meses(.data[[col_meses_med_enf]], 12) * 25
      } else { 0 },
      
      Pts_B = if (!is.null(col_simultaneo)) avaliar_simultaneo_b(.data[[col_simultaneo]]) * 25 else 0,
      Pts_C = if (!is.null(col_qtd_vd)) avaliar_visitas_c(.data[[col_qtd_vd]]) * 25 else 0,
      Pts_D = if (!is.null(col_influenza)) avaliar_vacina_d(.data[[col_influenza]]) * 25 else 0,
      
      Pontuacao_Total = Pts_A + Pts_B + Pts_C + Pts_D,
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
  
  cat("\nProcessamento da Pessoa Idosa concluído com sucesso! Arquivo salvo em:\n", caminho_saida)
} else {
  cat("\n❌ Erro: Nenhum arquivo .csv da pessoa idosa foi processado.\n")
}