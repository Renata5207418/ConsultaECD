# Consulta ECD - ReceitanetBX

Sistema web para importar uma planilha de empresas, consultar a existência de arquivos ECD pelo ReceitanetBX e exportar o resultado em Excel.

O fluxo principal é simples:

1. O usuário envia uma planilha `.xlsx`.
2. O sistema identifica os CNPJs da planilha.
3. O backend consulta o ReceitanetBX.
4. A tela acompanha o andamento da consulta.
5. O resultado fica disponível para visualização e exportação em Excel.

---

## Funcionalidades

* Importação de planilha `.xlsx`.
* Leitura automática da coluna `CNPJ`.
* Leitura opcional de código e razão social.
* Limpeza automática do CNPJ antes da consulta.
* Consulta da ECD por ano-calendário.
* Salvamento dos resultados no MongoDB.
* Acompanhamento do andamento pela tela.
* Filtro de resultados por status.
* Exportação dos resultados para Excel.

---

## Tecnologias utilizadas

* Python
* Flask
* MongoDB
* PyMongo
* Requests
* OpenPyXL
* HTML
* CSS
* JavaScript

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
|   `-- receitanetbx.py
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
`-- logs/
```

---

## Requisitos

Antes de rodar o sistema, é necessário ter:

* Python 3.12 ou superior.
* MongoDB rodando.
* Endpoint do ReceitanetBX acessível pela máquina onde o sistema está rodando.

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
Mesmo assim, é recomendado criar um arquivo `.env` na raiz do projeto para facilitar ajustes de ambiente, porta, MongoDB, endpoint do ReceitanetBX e pastas de arquivos.

Exemplo de `.env`:

```env
FLASK_HOST=0.0.0.0
FLASK_PORT=6550
FLASK_DEBUG=False

MONGO_URI=mongodb://localhost:27017
MONGO_DB=consulta_ecd

RECEITANETBX_ENDPOINT=http://127.0.0.1:2443/services/ReceitanetBX

UPLOAD_DIR=uploads
RESULT_DIR=resultados
```

### Observação sobre o endpoint

Se o ReceitanetBX estiver na mesma máquina do sistema, pode ser usado:

```env
RECEITANETBX_ENDPOINT=http://127.0.0.1:2443/services/ReceitanetBX
```

Se estiver em outra máquina da rede, use o IP da máquina onde o serviço está disponível.

Exemplo:

```env
RECEITANETBX_ENDPOINT=http://10.0.0.78:2443/services/ReceitanetBX
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

Ou, pela rede:

```text
http://IP_DO_SERVIDOR:6550
```

Exemplo:

```text
http://10.0.0.78:6550
```

---

## Formato da planilha

A planilha precisa estar em formato `.xlsx`.

A coluna obrigatória é:

```text
CNPJ
```

O sistema também tenta identificar automaticamente as colunas:

| Informação   | Nomes aceitos                                                          |
| ------------ | ---------------------------------------------------------------------- |
| Código       | `codigo`, `cod`, `código`, `codigo dominio`, `cod dominio`, `codi_emp` |
| Razão social | `razao social`, `razão social`, `empresa`, `nome`, `cliente`           |

Exemplo de planilha:

| Código | Razão Social         | CNPJ               |
| -----: | -------------------- | ------------------ |
|      3 | Empresa Exemplo LTDA | 06.872.037/0001-96 |
|      9 | Outra Empresa LTDA   | 08.909.630/0001-95 |

O sistema remove automaticamente pontos, barras e traços do CNPJ antes da consulta.

Exemplo:

```text
06.872.037/0001-96
```

Será consultado como:

```text
06872037000196
```

---

## Como usar

### 1. Nova consulta

Na tela `Nova Consulta`:

1. Selecione a planilha `.xlsx`.
2. Informe o ano-calendário.
3. Clique em `Importar e iniciar consultas`.

O sistema vai importar a planilha, criar os registros no MongoDB e iniciar as consultas.

---

### 2. Acompanhar andamento

Durante a execução, a tela mostra o resumo da consulta:

* Pendentes
* Consultando
* Encontradas
* Não encontradas
* Erros

Também é possível acompanhar a última mensagem de processamento e o último CNPJ consultado.

---

### 3. Ver resultados

Na tela `Resultados`, o usuário pode:

* visualizar os registros consultados;
* filtrar por status;
* reprocessar erros;
* exportar o resultado para Excel.

---

## Status possíveis

| Status           | Significado                                     |
| ---------------- | ----------------------------------------------- |
| `PENDENTE`       | Registro importado e aguardando consulta.       |
| `PROCESSANDO`    | Registro em consulta no momento.                |
| `ENCONTRADO`     | A Receita retornou arquivo ECD para o CNPJ/ano. |
| `NAO_ENCONTRADA` | Nenhum arquivo ECD foi encontrado.              |
| `CNPJ_INVALIDO`  | O CNPJ da planilha não possui 14 dígitos.       |
| `ERRO`           | Ocorreu erro na consulta ou no processamento.   |

---

## Exportação Excel

A exportação gera uma planilha com os resultados da consulta.

O arquivo contém informações como:

* Código
* Razão Social
* CNPJ
* Ano
* Status
* Mensagem retornada
* Quantidade de arquivos encontrados
* IDs dos arquivos
* Tentativas
* Data da consulta

---

## Logs

O sistema registra informações no terminal onde o `python main.py` está rodando.

Também pode registrar logs na pasta:

```text
logs/
```

Os logs ajudam a verificar se a consulta está realmente sendo enviada para o ReceitanetBX e qual retorno foi recebido.


## Comandos úteis

Rodar o sistema:

```bash
python main.py
```

Verificar se a aplicação responde:

```bash
curl http://localhost:6550/api/status
```

---

## Observações

Este sistema não utiliza automação visual ou robô de tela.

A consulta é feita pelo backend, usando o endpoint configurado do ReceitanetBX.

Para uso interno, o fluxo recomendado é:

1. iniciar o MongoDB;
2. iniciar o sistema com `python main.py`;
3. acessar a tela no navegador;
4. importar a planilha;
5. acompanhar a consulta;
6. exportar o Excel final.
