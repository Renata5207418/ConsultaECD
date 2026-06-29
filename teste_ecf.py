import html
import xml.etree.ElementTree as ET
import requests

ENDPOINT = "http://127.0.0.1:2443/services/ReceitanetBX"

# Dados reais que você pegou do log
CNPJ = "18335557000149"
ANO = 2024

SISTEMA = "SPED ECF"
TIPO_ARQUIVO = "Escrituração"

# Lista de todas as nomenclaturas bizarras que a RFB costuma usar
TENTATIVAS = [
    "Por Ano-Calendário",
    "Por Ano Calendário",
    "Ano Calendário",
    "Ano-Calendário",
    "Por Ano-calendário",
    "Por Ano-Calendario",
    "Período",
    "Por Período",
    "Por período",
    "Período de Apuração",
    "Por período de apuração",
    "Por Período da Escrituração",
    "Período da Escrituração",
    "Por data de entrega",
    "Por Período de Entrega",
    "Por Data de Transmissão"
]


def testar_brute_force():
    print("Iniciando varredura para descobrir a string secreta da ECF...\n")

    for pesquisa in TENTATIVAS:
        print(f"Testando: '{pesquisa}' ...", end=" ", flush=True)

        xml_entrada = f"""<pesquisa>
  <identificacao perfil="proc" sistema="{SISTEMA}" tipoarquivo="{TIPO_ARQUIVO}" tipopesquisa="{pesquisa}" nirepresentado="{CNPJ}" tiponirepresentado="cnpj" />
  <campo nome="dataInicio" valor="{ANO}-01-01" />
  <campo nome="dataFim" valor="{ANO}-12-31" />
</pesquisa>"""

        envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:axis2="http://ws.apache.org/axis2">
  <soapenv:Body>
    <axis2:PesquisarArquivos><axis2:entrada><![CDATA[{xml_entrada}]]></axis2:entrada></axis2:PesquisarArquivos>
  </soapenv:Body>
</soapenv:Envelope>"""

        try:
            response = requests.post(ENDPOINT, data=envelope.encode("utf-8"),
                                     headers={"Content-Type": "text/xml; charset=utf-8",
                                              "SOAPAction": "urn:PesquisarArquivos"})

            if response.status_code == 200:
                root = ET.fromstring(response.content)
                saida_el = root.find(".//{http://ws.apache.org/axis2}saida")
                saida_xml = html.unescape(saida_el.text if saida_el is not None else "").strip()

                # Se a resposta reclamar explicitamente do "tipo de pesquisa", a string está errada
                if "Não foi possível identificar o tipo de pesquisa" in saida_xml:
                    print("? Rejeitado")
                else:
                    print("\n\n? BINGO! ENCONTRAMOS A STRING CORRETA!")
                    print(f"-> Copie esta string: '{pesquisa}'")
                    print("\n--- RESPOSTA DA RECEITA FEDERAL ---")
                    print(saida_xml)
                    print("-----------------------------------\n")
                    return
            else:
                print(f"? Erro HTTP {response.status_code}")

        except Exception as e:
            print(f"Erro de conexão: {e}")


if __name__ == "__main__":
    testar_brute_force()
