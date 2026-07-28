import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd

# Função para remover os "namespaces" complexos do XML da NFe e facilitar a leitura
def limpar_namespace(tag):
    return tag.split('}')[-1] if '}' in tag else tag

# Função para ler o XML da NF original e extrair os produtos e impostos
def processar_xml_nf(arquivo_xml):
    tree = ET.parse(arquivo_xml)
    root = tree.getroot()
    
    produtos = []
    
    # Percorrendo todos os itens (detalhes) da nota fiscal
    for det in root.iter():
        if limpar_namespace(det.tag) == 'det':
            prod_info = {}
            # Buscando dados do produto dentro do bloco <prod>
            for prod in det.iter():
                tag = limpar_namespace(prod.tag)
                if tag == 'xProd':
                    prod_info['Nome'] = prod.text
                elif tag == 'qCom':
                    prod_info['Qtd Original'] = float(prod.text)
                elif tag == 'vUnCom':
                    prod_info['Valor Unitário'] = float(prod.text)
                elif tag == 'vProd':
                    prod_info['Valor Total Item'] = float(prod.text)
            
            # Buscando o ICMS (como exemplo de imposto) dentro do bloco <imposto>
            v_icms = 0.0
            for imposto in det.iter():
                tag = limpar_namespace(imposto.tag)
                if tag == 'vICMS':
                    v_icms = float(imposto.text)
            
            prod_info['ICMS Original'] = v_icms
            produtos.append(prod_info)
            
    return pd.DataFrame(produtos)

# Configuração da Interface Web
st.set_page_config(page_title="Gerador de Devolução NFe", layout="wide")
st.title("Espelho e Validador de NFD")

# Áreas de Upload
col1, col2 = st.columns(2)
with col1:
    nf_origem = st.file_uploader("1. Suba o XML da NF de Origem", type=["xml"])
with col2:
    nfd_devolucao = st.file_uploader("2. Suba o XML da NFD (Opcional - Para Conferência)", type=["xml"])

if nf_origem:
    st.success("NF de Origem carregada com sucesso!")
    df_produtos = processar_xml_nf(nf_origem)
    
    st.markdown("### Selecione as Quantidades para o Espelho da Devolução")
    
    total_devolucao = 0.0
    total_icms_devolucao = 0.0
    espelho_itens = []
    
    # Criação dos campos para cada produto encontrado no XML
    for index, linha in df_produtos.iterrows():
        nome = linha['Nome']
        qtd_orig = linha['Qtd Original']
        v_unit = linha['Valor Unitário']
        icms_orig = linha['ICMS Original']
        
        # Campo numérico para input do usuário
        qtd_dev = st.number_input(f"{nome} (Máx: {qtd_orig})", min_value=0.0, max_value=float(qtd_orig), value=0.0, step=1.0)
        
        if qtd_dev > 0:
            # Cálculo proporcional
            fator_proporcao = qtd_dev / qtd_orig
            valor_item_dev = qtd_dev * v_unit
            icms_item_dev = icms_orig * fator_proporcao
            
            # Somatório dos totais
            total_devolucao += valor_item_dev
            total_icms_devolucao += icms_item_dev
            
            espelho_itens.append({
                "Produto": nome,
                "Qtd Devolvida": qtd_dev,
                "Valor Devolvido": f"R$ {valor_item_dev:.2f}",
                "ICMS Devolvido": f"R$ {icms_item_dev:.2f}"
            })

    # Exibição do Resumo
    if espelho_itens:
        st.markdown("---")
        st.subheader("Resumo do Espelho de Devolução")
        st.table(pd.DataFrame(espelho_itens))
        
        st.markdown(f"**Valor Total dos Produtos Devolvidos:** R$ {total_devolucao:.2f}")
        st.markdown(f"**Valor Total de ICMS Proporcional:** R$ {total_icms_devolucao:.2f}")
        
        if nfd_devolucao:
            st.info("Lógica de conferência ativada: Aqui o sistema cruzará os dados acima com o XML da NFD (A ser implementado no próximo passo).")
