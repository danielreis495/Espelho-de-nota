import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
from fpdf import FPDF
import tempfile

# Função para remover as tags complexas do XML
def limpar_namespace(tag):
    return tag.split('}')[-1] if '}' in tag else tag

# Leitor avançado: Captura descontos, ICMS-ST e Número da Nota
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
                if tag in ['vICMS', 'vICMSST']:
                    prod_info['ICMS Original'] += float(imposto.text)
            
            prod_info['Valor Base'] = prod_info['Valor Total Item'] - prod_info['Desconto']
            produtos.append(prod_info)
            
    return pd.DataFrame(produtos), numero_nota

# Função para desenhar o arquivo PDF
def gerar_pdf(df, numero_nota):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"PRÉ-NOTA DE DEVOLUÇÃO - DOC: {numero_nota}", ln=True, align='C')
    pdf.ln(5) 
    
    pdf.set_font("Arial", 'B', 7)
    larguras = [40, 12, 18, 18, 18, 15, 18, 22, 22, 18, 15, 20, 20]
    colunas = df.columns.tolist()
    
    for i, col in enumerate(colunas):
        pdf.cell(larguras[i], 8, txt=str(col), border=1, align='C')
    pdf.ln()
    
    pdf.set_font("Arial", size=7)
    for index, row in df.iterrows():
        for i, item in enumerate(row):
            texto = f"{item:.2f}" if isinstance(item, (int, float)) else str(item)[:22]
            pdf.cell(larguras[i], 8, txt=texto, border=1, align='C')
        pdf.ln()
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        with open(tmp.name, "rb") as f:
            return f.read()

# Construção da Interface do Usuário (Layout Pré-Nota)
st.set_page_config(page_title="Emissão de Devolução", layout="wide")
st.title("📄 Sistema de Pré-Nota de Devolução")
st.markdown("---")

# Seção de Upload
col1, col2 = st.columns(2)
with col1:
    nf_origem = st.file_uploader("1. Anexe o XML da Nota Fiscal de Origem", type=["xml"])
with col2:
    nfd_devolucao = st.file_uploader("2. Anexe o XML da NFD para conferência (Opcional)", type=["xml"])

if nf_origem:
    df_produtos, numero_nota = processar_xml_nf(nf_origem)
    
    st.success("Documento processado com sucesso!")
    st.markdown(f"#### Referência: Nota Fiscal Nº `{numero_nota}`")
    st.write("Insira as quantidades dos itens que retornarão ao estoque:")
    
    espelho_itens = []
    
    # Variáveis para somar os totais da nota
    valor_liquido_total = 0.0
    icms_st_total = 0.0
    
    # Corpo da Nota: Seleção de Produtos
    with st.container():
        for index, linha in df_produtos.iterrows():
            nome = linha['Nome']
            qtd_orig = linha['Qtd Original']
            v_unit = linha['Valor Unitário']
            v_base_orig = linha['Valor Base']
            icms_orig = linha['ICMS Original']
            
            qtd_dev = st.number_input(f"📦 {nome} (Qtd. na NF: {qtd_orig})", min_value=0.0, max_value=float(qtd_orig), value=0.0, step=1.0)
            
            if qtd_dev > 0:
                fator_proporcao = qtd_dev / qtd_orig
                valor_item_dev = qtd_dev * v_unit
                icms_item_dev = icms_orig * fator_proporcao
                
                repasse = valor_item_dev * 0.8925
                desc = repasse * 0.08
                vl_liq = repasse - desc
                
                # Incrementando os totais gerais da nota
                valor_liquido_total += vl_liq
                icms_st_total += icms_item_dev
                
                espelho_itens.append({
                    "PRODUTO": nome,
                    "QTE": qtd_dev,
                    "VL UNIT": v_unit,
                    "VL TOTAL": valor_item_dev,
                    "REPASSE": repasse,
                    "DESC": desc,
                    "VL LIQ": vl_liq,
                    "VL UNIT (PMC)": 0.0,
                    "VL TOTAL(PMC)": 0.0,
                    "REDUÇÃO": 0.0,
                    "BASE": v_base_orig * fator_proporcao,
                    "ALÍQUOTA": 18.0,
                    "ICMS ST": icms_item_dev
                })

    # Rodapé: Exibição da Tabela e Totais
    if espelho_itens:
        df_final = pd.DataFrame(espelho_itens)
        
        st.markdown("---")
        st.markdown("### Resumo dos Itens Devolvidos")
        st.dataframe(df_final.style.format(precision=2), use_container_width=True)
        
        st.markdown("---")
        st.markdown("### Totais da Devolução")
        
        # Painel contábil dividido em 3 colunas
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1:
            st.metric(label="Volume de Itens Diferentes", value=len(espelho_itens))
        with col_t2:
            st.metric(label="Total de ICMS-ST Calculado", value=f"R$ {icms_st_total:.2f}")
        with col_t3:
            st.metric(label="VALOR LÍQUIDO TOTAL", value=f"R$ {valor_liquido_total:.2f}")
        
        st.markdown("---")
        
        # Botão destacado
        pdf_pronto = gerar_pdf(df_final, numero_nota)
        st.download_button(
            label="📄 Emitir Pré-Nota em PDF",
            data=pdf_pronto,
            file_name=f"Pre_Nota_Devolucao_{numero_nota}.pdf",
            mime="application/pdf",
            type="primary" 
        )
