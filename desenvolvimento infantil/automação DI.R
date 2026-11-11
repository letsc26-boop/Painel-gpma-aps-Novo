# =========================================================
# 1. CARREGAR AS BIBLIOTECAS
# =========================================================
library(tidyverse)
library(data.table)

# =========================================================
# 2. CONFIGURAR OS CAMINHOS DE ENTRADA E SAÍDA
# =========================================================
pasta_entrada <- "W:/GPMA/NCAIS/Residência/Letícia Stefany Costa/arquivos e-sus/DI PARA R/6 DE NOVEMBRO"
caminho_saida  <- "W:/GPMA/NCAIS/Residência/Letícia Stefany Costa/Relatorio indicadores de saúde/desenvolvimento infantil/arquivos csv/6 de novembro.csv"

# Listar todos os arquivos .csv dentro da pasta
arquivos <- list.files(path = pasta_entrada, pattern = "\\.csv$", full.names = TRUE)
lista_dados_equipes <- list()

# =========================================================
# 3. LOOP PARA PROCESSAR ARQUIVO POR ARQUIVO
# =========================================================
for (arquivo in arquivos) {
  
  cat("Processando o arquivo:", basename(arquivo), "\n")
  
  # -------------------------------------------------------
  # A. CAPTURAR E EXTRAIR A UBS AUTOMATICAMENTE (LINHA 5)
  # -------------------------------------------------------
  linhas_texto <- read_lines(arquivo, skip = 4, n_max = 1, locale = locale(encoding = "Latin1"))
  nome_ubs_limpo <- str_extract(linhas_texto, "UBS[^;]+") %>% str_trim()
  
  if (is.na(nome_ubs_limpo) || nome_ubs_limpo == "") {
    nome_ubs_limpo <- "UBS DESCONHECIDA" 
  }
  
  # -------------------------------------------------------
  # B. CAPTURAR E EXTRAIR O NOME DA EQUIPE AUTOMATICAMENTE (LINHA 10)
  # -------------------------------------------------------
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
  
  # -------------------------------------------------------
  # 🔮 DIFERENCIAR APENAS AS REAIS GÊMEAS
  # -------------------------------------------------------
  equipes_gemeas <- c("EQUIPE AMARELA", "EQUIPE AZUL", "EQUIPE LILAS", 
                      "EQUIPE VERDE", "EQUIPE VERMELHA")
  
  if (nome_equipe_limpo %in% equipes_gemeas) {
    if (str_detect(nome_ubs_limpo, "UBS 2 ASA NORTE")) {
      nome_equipe_limpo <- paste0(nome_equipe_limpo, "_AN")
    } else if (str_detect(nome_ubs_limpo, "UBS 1 ASA SUL")) {
      nome_equipe_limpo <- paste0(nome_equipe_limpo, "_AS")
    }
  }
  
  # -------------------------------------------------------
  # C. LEITURA DOS DADOS DA PLANILHA (Pulo de 24 linhas garantido!)
  # -------------------------------------------------------
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
  
  # -------------------------------------------------------
  # D. MAPEAMENTO FLEXÍVEL DE COLUNAS POR PALAVRAS-CHAVE
  # -------------------------------------------------------
  n <- names(dados_brutos)
  
  col_idade_prim_cons <- n[str_detect(n, regex("Idade.*primeira", ignore_case = TRUE))][1]
  col_qtd_cons        <- n[str_detect(n, regex("Quantidade.*consultas", ignore_case = TRUE))][1]
  col_qtd_peso_alt    <- n[str_detect(n, regex("Quantidade.*medicoes.*peso|peso.*altura", ignore_case = TRUE))][1]
  col_qtd_visitas     <- n[str_detect(n, regex("Quantidade.*visitas.*domiciliares", ignore_case = TRUE))][1]
  col_visitas_ult     <- n[str_detect(n, regex("Últimas visitas|visitas domiciliares", ignore_case = TRUE))][1]
  
  col_vac_penta       <- n[str_detect(n, regex("Difteria|Penta", ignore_case = TRUE))][1]
  col_vac_polio       <- n[str_detect(n, regex("Poliomielite", ignore_case = TRUE))][1]
  col_vac_trpl        <- n[str_detect(n, regex("Sarampo|Caxumba", ignore_case = TRUE))][1]
  col_vac_pneu        <- n[str_detect(n, regex("Pneumocócica", ignore_case = TRUE))][1]
  
  # -------------------------------------------------------
  # E. TRATAMENTO E AVALIAÇÃO DOS CRITÉRIOS DE DESENVOLVIMENTO INFANTIL
  # -------------------------------------------------------
  dados_processados <- dados_brutos %>%
    # REMOVER COLUNAS SENSÍVEIS E DE IDENTIFICAÇÃO INDIVIDUAL
    select(
      -matches(
        "Nome|CPF|CNS|Telefone|médico|enfermagem|odontológico|problemas|Titular.*Bolsa|Vigência",
        ignore.case = TRUE
      )
    ) %>%
    
    # Converter colunas numéricas de contagem para análises lógicas
    mutate(
      across(matches("Quantidade|Doses"), ~ suppressWarnings(as.numeric(.))),
      
      # A) 1ª consulta realizada por médico(a) ou enfermeiro(a) até o 30º dia de vida.
      Criterio_A_1Consulta30Dias = case_when(
        !is.na(col_idade_prim_cons) & col_idade_prim_cons %in% names(.) & 
          str_detect(.data[[col_idade_prim_cons]], "dia") & 
          suppressWarnings(as.numeric(str_extract(.data[[col_idade_prim_cons]], "\\d+"))) <= 30 ~ "SIM",
        TRUE ~ "NÃO"
      ),
      
      # B) Pelo menos 09 consultas presenciais ou remotas até dois anos de vida
      Criterio_B_9Consultas2Anos = case_when(
        !is.na(col_qtd_cons) & col_qtd_cons %in% names(.) & 
          !is.na(.data[[col_qtd_cons]]) & suppressWarnings(as.numeric(.data[[col_qtd_cons]])) >= 9 ~ "SIM",
        TRUE ~ "NÃO"
      ),
      
      # C) Pelo menos 09 registros simultâneos de peso e altura até os dois anos
      Criterio_C_9PesosAlturas = case_when(
        !is.na(col_qtd_peso_alt) & col_qtd_peso_alt %in% names(.) & 
          !is.na(.data[[col_qtd_peso_alt]]) & suppressWarnings(as.numeric(.data[[col_qtd_peso_alt]])) >= 9 ~ "SIM",
        TRUE ~ "NÃO"
      ),
      
      # D) Pelo menos 02 visitas domiciliares realizadas por ACS/TACS
      Criterio_D_2VisitasDom = case_when(
        !is.na(col_qtd_visitas) & col_qtd_visitas %in% names(.) & 
          !is.na(.data[[col_qtd_visitas]]) & suppressWarnings(as.numeric(.data[[col_qtd_visitas]])) >= 2 ~ "SIM",
        TRUE ~ "NÃO"
      ),
      
      # E) Vacinas essenciais completas
      Criterio_E_VacinasCompletas = case_when(
        !is.na(col_vac_penta) & col_vac_penta %in% names(.) &
          !is.na(col_vac_polio) & col_vac_polio %in% names(.) &
          !is.na(col_vac_trpl) & col_vac_trpl %in% names(.) &
          !is.na(col_vac_pneu) & col_vac_pneu %in% names(.) &
          str_detect(.data[[col_vac_penta]], "D3|R1|Ref") &
          str_detect(.data[[col_vac_polio]], "D3|R1|Ref") &
          str_detect(.data[[col_vac_trpl]], "D1|DU") &
          str_detect(.data[[col_vac_pneu]], "D2|REF") ~ "SIM",
        TRUE ~ "NÃO"
      ),
      
      # Indicador Global / Consolidado da Criança
      Atingiu_Todas_Boas_Praticas = if_else(
        Criterio_A_1Consulta30Dias == "SIM" &
          Criterio_B_9Consultas2Anos == "SIM" &
          Criterio_C_9PesosAlturas == "SIM" &
          Criterio_D_2VisitasDom == "SIM" &
          Criterio_E_VacinasCompletas == "SIM",
        "SIM", "NÃO"
      ),
      
      DATA = as.character(Sys.Date()), 
      UBS = nome_ubs_limpo,        
      EQUIPE = nome_equipe_limpo,
      IDENTIFICAÇÃO = NA_character_
    ) %>%
    
    # Organização das colunas padrão
    relocate(DATA, UBS, EQUIPE, IDENTIFICAÇÃO, .before = everything()) %>% 
    relocate(IDENTIFICAÇÃO, .after = DATA)
  
  # Separar as datas de visitas domiciliares caso venham coladas no texto original
  if (length(col_visitas_ult) > 0 && !is.na(col_visitas_ult[1]) && col_visitas_ult[1] %in% names(dados_processados)) {
    dados_processados <- dados_processados %>%
      separate(
        col = all_of(col_visitas_ult[1]),
        into = c("Datas_1ªVisitaDomiciliar", "Datas_2ªVisitaDomiciliar"),
        sep = " e ",
        remove = FALSE,
        fill = "right"
      )
  }
  
  lista_dados_equipes[[arquivo]] <- dados_processados
}

# =========================================================
# 4. CONSOLIDAR TODAS AS EQUIPES E EXPORTAR
# =========================================================
if (length(lista_dados_equipes) > 0) {
  dados_finais_consolidados <- bind_rows(lista_dados_equipes)
  
  fwrite(
    dados_finais_consolidados,
    caminho_saida,
    sep = ";",
    bom = TRUE,
    na = ""
  )
  
  cat(
    "\nAutomação do Desenvolvimento Infantil concluída com sucesso!\n",
    "Foram processadas", length(lista_dados_equipes), "equipes.\n",
    "Arquivo final salvo em:\n", caminho_saida
  )
} else {
  cat("\n❌ Erro: Nenhum arquivo .csv válido foi processado.\n")
}