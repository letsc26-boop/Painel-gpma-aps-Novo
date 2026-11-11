# ==============================================================================
# MONITORAMENTO APS - CUIDADO DA MULHER NA PREVENÇÃO DO CÂNCER (NOTA C7)
# ==============================================================================

library(tidyverse)
library(lubridate)
library(data.table)

# 1. Definir caminhos de entrada e saída (Ajuste conforme sua estrutura)
pasta_entrada <- "W:/GPMA/NCAIS/Residência/Letícia Stefany Costa/arquivos e-sus/salvar esusmulher/9 de novembro"
caminho_saida <- "W:/GPMA/NCAIS/Residência/Letícia Stefany Costa/Relatorio indicadores de saúde/Mulher/arquivos csv/9 de novembro.csv"

# Garantir que o diretório de saída existe
dir.create(dirname(caminho_saida), recursive = TRUE, showWarnings = FALSE)

arquivos <- list.files(path = pasta_entrada, pattern = "\\.csv$", full.names = TRUE)

if (length(arquivos) == 0) {
  stop("Nenhum arquivo CSV encontrado na pasta de Câncer/Mulher especificada!")
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
  
  # D. Leitura dos dados da tabela (Cabeçalho na linha 25 / skip = 24)
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
  
  # E. Mapeamento dinâmico das colunas da Nota C7
  obter_coluna <- function(df, padrao) {
    col <- names(df)[str_detect(names(df), regex(padrao, ignore_case = TRUE))]
    if (length(col) > 0) return(col[1]) else return(NULL)
  }
  
  col_atend_ssr  <- obter_coluna(dados_brutos, "Data da última consulta de saúde sexual")
  col_colo_aval  <- obter_coluna(dados_brutos, "câncer de colo de útero.*última avaliação")
  col_mama_aval  <- obter_coluna(dados_brutos, "câncer de mama.*última avaliação")
  col_hpv        <- obter_coluna(dados_brutos, "^HPV$")
  
  # Funções auxiliares de avaliação para C7
  avaliar_colo_a <- function(val) {
    v <- toupper(coalesce(val, ""))
    if_else(v != "" & v != "-" & v != "SEM REGISTRO" & !str_detect(v, "NÃO REALIZADO"), 1, 0)
  }
  
  avaliar_hpv_b <- function(val) {
    v <- toupper(coalesce(val, ""))
    if_else(v != "" & v != "SEM REGISTRO" & v != "-" & str_detect(v, "HPV|67|93"), 1, 0)
  }
  
  avaliar_ssr_c <- function(val) {
    s <- str_trim(coalesce(as.character(val), ""))
    if (s == "" || s == "-" || s == "SEM REGISTRO") return(0)
    dt <- dmy(s, quiet = TRUE)
    if (is.na(dt)) dt <- ymd(s, quiet = TRUE)
    if (is.na(dt)) return(0)
    
    diff_meses <- interval(dt, Sys.Date()) / months(1)
    if_else(diff_meses <= 12 && diff_meses >= 0, 1, 0)
  }
  
  avaliar_mama_d <- function(val) {
    s <- str_trim(coalesce(as.character(val), ""))
    if (s == "" || s == "-" || s == "SEM REGISTRO") return(0)
    dt <- dmy(s, quiet = TRUE)
    if (is.na(dt)) dt <- ymd(s, quiet = TRUE)
    if (is.na(dt)) return(1)
    
    diff_meses <- interval(dt, Sys.Date()) / months(1)
    if_else(diff_meses <= 24 && diff_meses >= 0, 1, 0)
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
      
      # Pontuação Individual (Nota C7) - Corrigido com .data[[...]]
      Pts_A = if (!is.null(col_colo_aval)) sapply(.data[[col_colo_aval]], avaliar_colo_a) * 20 else 0,
      Pts_B = if (!is.null(col_hpv)) sapply(.data[[col_hpv]], avaliar_hpv_b) * 30 else 0,
      Pts_C = if (!is.null(col_atend_ssr)) sapply(.data[[col_atend_ssr]], avaliar_ssr_c) * 30 else 0,
      Pts_D = if (!is.null(col_mama_aval)) sapply(.data[[col_mama_aval]], avaliar_mama_d) * 20 else 0,
      
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
  
  cat("\nProcessamento da Prevenção do Câncer (Mulher) concluído! Arquivo salvo em:\n", caminho_saida)
} else {
  cat("\n❌ Erro: Nenhum arquivo .csv foi processado.\n")
}