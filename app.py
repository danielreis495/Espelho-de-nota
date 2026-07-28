import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
from fpdf import FPDF
import tempfile

# 1. Função para remover os namespaces do XML
def limpar_namespace(tag):
    return tag.split('}')[-1] if '}' in tag else tag

# 2. Leitor rigoroso do XML: Extrai apenas o que está declarado na nota
def processar_xml_nf(arquivo_xml):
    tree = ET.parse(arquivo_xml)
    root = tree.getroot()
    
    numero_nota = "Não encontrado"
    produtos = []
    
    for ide in root.iter():
        if limpar_namespace(ide.tag) == 'ide':
            for nNF in ide.iter():
                if limpar_namespace(nNF.tag) == 'nNF':
                    numero_nota = nNF.text
                    break
            break
            
    for det in root.iter():
        if limpar_namespace(det.tag) == 'det':
            prod_info = {
                'Nome': '', 'Qtd Original': 0.0, 'Valor Unitário': 0.0, 
                'Valor Total Item': 0.0, 'Desconto': 0.0, 'ICMS Original': 0.0
            }
            
            for prod in det.iter():
                tag = limpar_namespace(prod.tag)
                if tag == 'xProd': prod_info['Nome'] = prod.text
                elif tag == 'qCom': prod_info['Qtd Original'] = float(prod.text)
                elif tag == 'vUnCom': prod_info['Valor Unitário'] = float(prod.text)
                elif tag == 'vProd': prod_info['Valor Total Item'] = float(prod.text)
                elif tag == 'vDesc': prod_info['Desconto'] = float(prod.text)
            
            for imposto in det.iter():
                tag = limpar_namespace(imposto.tag)
                if tag == 'vICMS':
                    prod_info['ICMS Original'] += float(imposto.text)
            
            prod_info['Valor Base'] = prod_info['Valor Total Item'] - prod_info['Desconto']
            produtos.append(prod_info)
            
    return pd.DataFrame(produtos), numero_nota

# 3. Gerador de PDF alinhado aos dados reais
def gerar_pdf(df, numero_nota, valor_liq_total, icms_total):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, "SISTEMA DE PRÉ-NOTA DE DEVOLUÇÃO", ln=True, align='C')
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, f"Nota Fiscal de Origem Nº: {numero_nota}", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 8)
    larguras = [70, 15, 25, 30, 25, 25, 30, 25]
    colunas = df.columns.tolist()
    
    pdf.set_fill_color(240, 240, 240)
    for i, col in enumerate(colunas):
        pdf.cell(larguras[i], 7, txt=str(col), border=1, align='C', fill=True)
    pdf.ln()
    
    pdf.set_font("Arial", size=8)
    for index, row in df.iterrows():
        for i, item in enumerate(row):
            texto = f"{item:.2f}" if isinstance(item, (int, float)) else str(item)[:35]
            pdf.cell(larguras[i], 6, txt=texto, border=1, align='C')
        pdf.ln()
        
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(0, 6, "TOTAIS DA DEVOLUÇÃO:", ln=True)
    pdf.set_font("Arial", size=9)
    pdf.cell(0, 6, f"Total de ICMS Calculado: R$ {icms_total:.2f}", ln=True)
    pdf.cell(0, 6, f"VALOR LÍQUIDO TOTAL DA DEVOLUÇÃO: R$ {valor_liq_total:.2f}", ln=True)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        with open(tmp.name, "rb") as f:
            return f.read()

# 4. Interface Web do Aplicativo
st.set_page_config(page_title="Emissão de Devolução", layout="wide")
st.title("📄 Sistema de Pré-Nota de Devolução")
st.markdown("---")

# Apenas o upload da nota de origem (campo único)
nf_origem = st.file_uploader("Anexe o XML da Nota Fiscal de Origem", type=["xml"])

if nf_origem:
    df_produtos, numero_nota = processar_xml_nf(nf_origem)
    
    st.success("Documento processado com sucesso!")
    st.markdown(f"#### Referência: Nota Fiscal Nº `{numero_nota}`")
    st.write("Insira as quantidades dos itens que retornarão ao estoque:")
    
    espelho_itens = []
    valor_liquido_total = 0.0
    icms_normal_total = 0.0
    
    with st.container():
        for index, linha in df_produtos.iterrows():
            nome = linha['Nome']
            qtd_orig = linha['Qtd Original']
            v_unit = linha['Valor Unitário']
            v_base_orig = linha['Valor Base']
            icms_orig = linha['ICMS Original']
            desconto_orig = linha['Desconto']
            
            # Campo numérico ajustado para capturar corretamente a quantidade inteira/decimal
            qtd_dev = st.number_input(
                f"📦 {nome} (Qtd. na NF: {int(qtd_orig)})", 
                min_value=0.0, 
                max_value=float(qtd_orig), 
                value=0.0, 
                step=1.0,
                format="%.0f"
            )
            
            if qtd_dev > 0:
                fator_proporcao = qtd_dev / qtd_orig
                valor_item_dev = qtd_dev * v_unit
                icms_item_dev = icms_orig * fator_proporcao
                desconto_item_dev = desconto_orig * fator_proporcao
                
                vl_liq_item = valor_item_dev - desconto_item_dev
                
                valor_liquido_total += vl_liq_item
                icms_normal_total += icms_item_dev
                
                espelho_itens.append({
                    "PRODUTO": nome,
                    "QTE": qtd_dev,
                    "VL UNIT": v_unit,
                    "DESCONTO": desconto_item_dev,
                    "VL TOTAL": valor_item_dev,
                    "VL LÍQUIDO": vl_liq_item,
                    "BASE ICMS": v_base_orig * fator_proporcao,
                    "ICMS": icms_item_dev
                })

    if espelho_itens:
        df_final = pd.DataFrame(espelho_itens)
        
        st.markdown("---")
        st.markdown("### Resumo dos Itens Devolvidos")
        st.dataframe(df_final.style.format(precision=2), use_container_width=True)
        
        st.markdown("---")
        st.markdown("### Totais da Devolução")
        
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1:
            st.metric(label="Volume de Itens Diferentes", value=len(espelho_itens))
        with col_t2:
            st.metric(label="Total de ICMS Calculado", value=f"R$ {icms_normal_total:.2f}")
        with col_t3:
            st.metric(label="VALOR LÍQUIDO TOTAL", value=f"R$ {valor_liquido_total:.2f}")
        
        st.markdown("---")
        
        pdf_pronto = gerar_pdf(df_final, numero_nota, valor_liquido_total, icms_normal_total)
        st.download_button(
            label="📄 Emitir Pré-Nota em PDF",
            data=pdf_pronto,
            file_name=f"Pre_Nota_Devolucao_{numero_nota}.pdf",
            mime="application/pdf",
            type="primary"
        )
