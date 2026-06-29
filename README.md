# Consulta ECD | ECF - ReceitanetBX

Sistema web para importar uma planilha de empresas, consultar a existência de arquivos ECD e ECF pelo ReceitanetBX, realizar o download automático dos arquivos encontrados e exportar os resultados consolidados (Excel e ZIP).

O fluxo principal é simples:

1. O usuário envia uma planilha `.xlsx` e seleciona o tipo de declaração (ECD ou ECF).
2. O sistema identifica os CNPJs e cria uma fila de processamento.
3. O backend consulta o ReceitanetBX (e solicita os arquivos, caso desejado).
4. O sistema monitora a pasta do ReceitanetBX e identifica os arquivos baixados automaticamente.
5. A tela acompanha o andamento da consulta e dos downloads em tempo real.
6. O resultado fica disponível para visualização, exportação em Excel e download em ZIP.

> ⚠️ **AVISO IMPORTANTE**: Este sistema não acessa a base da Receita Federal diretamente pela internet.
Ele atua como uma interface de automação que se comunica com o aplicativo oficial ReceitanetBX. 
Portanto, é obrigatório ter o ReceitanetBX Serviços instalado e rodando na máquina para que as consultas e downloads funcionem.
---

## Funcionalidades

* Importação de planilha `.xlsx`.
* Leitura automática da coluna `CNPJ` (ignorando formatações).
* Leitura opcional de `Código` e `Razão Social`.
* Consulta de **ECD** ou **ECF** por ano-calendário.
* Solicitação e monitoramento automático de **downloads** de arquivos.
* Geração de lote em arquivo **.ZIP** com todas as declarações baixadas.
* Salvamento dos resultados no MongoDB.
* Acompanhamento do andamento e progresso (X de Z) ao vivo pela tela.
* Paginação de resultados e busca rápida (CNPJ, Código ou Nome).
* Filtro de resultados por status em formato de menu suspenso.
* Exportação do relatório final para Excel (.xlsx).

---

## Tecnologias utilizadas

* Python (Flask)
* MongoDB (PyMongo)
* Requests (Integração SOAP)
* OpenPyXL (Leitura e gravação de Excel)
* HTML5, CSS3 e Vanilla JavaScript

---

## Estrutura do projeto

```text
consulta_ecd/
|
|-- main.py
|-- api.py
|-- worker.py
|-- database.py
|-- config.py
|-- .env
|
|-- services/
|   |-- __init__.py
|   |-- planilha.py
|   |-- receitanetbx.py
|   |-- downloads_lote.py
|   `-- downloads_receitanetbx.py
|
|-- templates/
|   `-- index.html
|
|-- static/
|   |-- app.js
|   `-- style.css
|
|-- uploads/
|-- resultados/
|-- zips/
`-- logs/

```

---

## Requisitos

Antes de rodar o sistema, é necessário ter:

1. **Python 3.12** ou superior.
2. Banco de dados **MongoDB** rodando.
3. **ReceitanetBX-Serviços (Receita Federal)** instalado e rodando em modo **Web Service** na **mesma máquina** que a aplicação. Por restrição de segurança da própria Receita Federal, a API bloqueia acessos externos via rede, aceitando apenas requisições via `localhost` (127.0.0.1).

---

## Instalação

Crie o ambiente virtual:

```bash
python -m venv .venv

```

Ative o ambiente virtual.

No Windows:

```bash
.venv\Scripts\activate

```

No Linux:

```bash
source .venv/bin/activate

```

Instale as dependências:

```bash
pip install flask pymongo python-dotenv requests openpyxl

```

---

## Configuração

O sistema pode rodar sem arquivo `.env`, pois o `config.py` já possui valores padrão.
Mesmo assim, é recomendado criar um arquivo `.env` na raiz do projeto para configurar caminhos essenciais, como as pastas de download do ReceitanetBX.

Exemplo de `.env`:

```env
FLASK_HOST=0.0.0.0
FLASK_PORT=6550
FLASK_DEBUG=False

MONGO_URI=mongodb://localhost:27017
MONGO_DB=consulta_ecd

RECEITANETBX_ENDPOINT=http://127.0.0.1:2443/services/ReceitanetBX

# Pastas locais do sistema
UPLOAD_DIR=uploads
RESULT_DIR=resultados
ZIP_DIR=resultados/zips

# Pastas de integração com o aplicativo ReceitanetBX
RECEITANETBX_DOWNLOAD_DIR=C:\Arquivos_ReceitanetBX\Downloads
RECEITANETBX_LOG_DIR=C:\Arquivos_ReceitanetBX\log

```

---

## Como rodar

Com o ambiente virtual ativado, execute:

```bash
python main.py

```

Depois acesse no navegador:

```text
http://localhost:6550

```

---

## Formato da planilha

A planilha precisa estar em formato `.xlsx`.

A coluna obrigatória é: `CNPJ`

O sistema também tenta identificar automaticamente as colunas:

| Informação | Nomes aceitos |
| --- | --- |
| Código | `codigo`, `cod`, `código`, `codigo dominio`, `cod dominio`, `codi_emp` |
| Razão social | `razao social`, `razão social`, `empresa`, `nome`, `cliente` |

A leitura ocorre estritamente na **primeira aba** (Worksheet) do arquivo importado. O sistema remove automaticamente pontos, barras e traços do CNPJ antes da consulta.

---

## Como usar

### 1. Nova consulta

Na tela `Nova Consulta`:

1. Envie a planilha `.xlsx`.
2. Informe o **ano-calendário**.
3. Selecione o **Tipo de Declaração** (`ECD` ou `ECF`).
4. Marque a caixa se desejar que o sistema solicite e monitore os downloads automaticamente.
5. Clique em `Importar e iniciar consultas`.

O sistema vai importar a primeira aba da planilha, criar a fila no banco e iniciar o worker em segundo plano.

---

### 2. Acompanhar andamento

Durante a execução, a tela "Nova Consulta" mostra o resumo ao vivo:

* **Cards superiores:** Baixadas, Não encontradas, Erros.
* **Live Box:** Mostra o progresso percentual (X de Z), último CNPJ processado, status atual e horário.

---

### 3. Ver resultados e Exportar

Na tela `Resultados`, o usuário pode:

* Navegar pela tabela utilizando a **paginação** e a **barra de busca rápida** (CNPJ, nome ou código).
* Filtrar os resultados por **status** clicando no ícone de funil no cabeçalho da tabela.
* Fazer o download de um arquivo individual na coluna "Arquivo".
* Clicar em **Baixar ZIP** para compilar todos os arquivos encontrados em um único pacote.
* Clicar em **Exportar Excel** para baixar o relatório final da operação.
* **Reprocessar erros:** Devolve consultas falhas para a fila (`PENDENTE`) e tenta novamente.

---

## Status possíveis

| Status | Significado |
| --- | --- |
| `PENDENTE` | Registro importado e aguardando consulta no topo da fila. |
| `PROCESSANDO` | O sistema está se comunicando com o ReceitanetBX neste exato momento. |
| `ENCONTRADO` | A declaração (ECD/ECF) foi encontrada, mas não foi solicitado download. |
| `SOLICITADO` | Declaração encontrada e solicitação de download enviada com sucesso. |
| `AGUARDANDO_DOWNLOAD` | Pedido registrado; o sistema está escaneando a pasta do ReceitanetBX. |
| `BAIXADO` | O arquivo foi localizado com sucesso na pasta de downloads. |
| `ARQUIVO_NAO_LOCALIZADO` | Esgotou o tempo limite e o arquivo físico não apareceu na pasta. |
| `NAO_ENCONTRADA` | Nenhuma declaração (ECD/ECF) foi encontrada para o CNPJ e Ano. |
| `CNPJ_INVALIDO` | O CNPJ da planilha não possui os 14 dígitos requeridos. |
| `ERRO` / `ERRO_DOWNLOAD` | Ocorreu erro de sistema, timeout ou recusa do serviço SOAP. |

---

## Logs e Arquivos Gerados

* O terminal da aplicação e o arquivo gerado em `logs/consulta_ecd.log` guardam os rastros detalhados de cada consulta e request SOAP.
* A exportação em Excel gera um arquivo inteligente (`resultado_ecd...` ou `resultado_ecf...`) na pasta configurada de resultados.
* O download em lote varre os registros de sucesso e cria um `.zip` com pastas separadas por cliente, evitando sobreposição de nomes.