import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd

# 1. Função para remover as tags complexas do XML e facilitar a leitura
def limpar_namespace(tag):
    return tag.split('}')[-1] if '}' in tag else tag

# 2. Leitor avançado: Agora captura descontos e Substituição Tributária (ICMS-ST)
def processar_xml_nf(arquivo_xml):
    tree = ET.parse(arquivo_xml)
    root = tree.getroot()
    produtos = []
    
    for det in root.iter():
        if limpar_namespace(det.tag) == 'det':
            # Dicionário inicial zerado para evitar erros se a tag não existir na nota
            prod_info = {
                'Nome': '', 'Qtd Original': 0.0, 'Valor Total Item': 0.0,
                'Desconto': 0.0, 'ICMS Original': 0.0
            }
            
            # Vasculha os dados de preço e desconto do produto
            for prod in det.iter():
                tag = limpar_namespace(prod.tag)
                if tag == 'xProd': prod_info['Nome'] = prod.text
                elif tag == 'qCom': prod_info['Qtd Original'] = float(prod.text)
                elif tag == 'vProd': prod_info['Valor Total Item'] = float(prod.text)
                elif tag == 'vDesc': prod_info['Desconto'] = float(prod.text)
            
            # Vasculha os impostos (Importante para produtos farmacêuticos)
            for imposto in det.iter():
                tag = limpar_namespace(imposto.tag)
                if tag in ['vICMS', 'vICMSST']:
                    prod_info['ICMS Original'] += float(imposto.text)
            
            # Calcula o valor líquido real da linha
            prod_info['Valor Base'] = prod_info['Valor Total Item'] - prod_info['Desconto']
            produtos.append(prod_info)
            
    return pd.DataFrame(produtos)

# 3. Construção da Interface do Usuário
st.set_page_config(page_title="Gerador de Devolução NFe", layout="wide")
st.title("Espelho e Validador de NFD")

col1, col2 = st.columns(2)
with col1:
    nf_origem = st.file_uploader("1. Suba o XML da NF de Origem", type=["xml"])
with col2:
    nfd_devolucao = st.file_uploader("2. Suba o XML da NFD (Opcional - Para Conferência)", type=["xml"])

# 4. Motor de Cálculo Proporcional
if nf_origem:
    st.success("NF de Origem carregada com sucesso!")
    df_produtos = processar_xml_nf(nf_origem)
    
    st.markdown("### Selecione as Quantidades para o Espelho da Devolução")
    
    total_devolucao = 0.0
    total_icms_devolucao = 0.0
    espelho_itens = []
    
    for index, linha in df_produtos.iterrows():
        nome = linha['Nome']
        qtd_orig = linha['Qtd Original']
        v_base_orig = linha['Valor Base']
        icms_orig = linha['ICMS Original']
        
        qtd_dev = st.number_input(f"{nome} (Máx: {qtd_orig})", min_value=0.0, max_value=float(qtd_orig), value=0.0, step=1.0)
        
        if qtd_dev > 0:
            # A matemática principal: cria uma % de devolução e aplica aos valores
            fator_proporcao = qtd_dev / qtd_orig
            valor_item_dev = v_base_orig * fator_proporcao
            icms_item_dev = icms_orig * fator_proporcao
            
            total_devolucao += valor_item_dev
            total_icms_devolucao += icms_item_dev
            
            espelho_itens.append({
                "Produto": nome,
                "Qtd Devolvida": qtd_dev,
                "Valor Devolvido": f"R$ {valor_item_dev:.2f}",
                "ICMS Devolvido": f"R$ {icms_item_dev:.2f}"
            })

    # 5. Exibição dos Resultados
    if espelho_itens:
        st.markdown("---")
        st.subheader("Resumo do Espelho de Devolução")
        st.table(pd.DataFrame(espelho_itens))
        
        st.markdown(f"**Valor Total dos Produtos Devolvidos:** R$ {total_devolucao:.2f}")
        st.markdown(f"**Valor Total de ICMS Proporcional:** R$ {total_icms_devolucao:.2f}")
