import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
from fpdf import FPDF
import tempfile

# 1. Função para remover os namespaces do XML
def limpar_namespace(tag):
    return tag.split('}')[-1] if '}' in tag else tag

# 2. Leitor rigoroso do XML: Extrai dados fiscais, cliente, transporte e produtos
def processar_xml_nf(arquivo_xml):
    tree = ET.parse(arquivo_xml)
    root = tree.getroot()
    
    numero_nota = "Não encontrado"
    cliente_nome = "Não informado"
    cidade = ""
    uf = ""
    transportadora = "Não informada"
    produtos = []
    
    # Captura o número da nota
    for ide in root.iter():
        if limpar_namespace(ide.tag) == 'ide':
            for nNF in ide.iter():
                if limpar_namespace(nNF.tag) == 'nNF':
                    numero_nota = nNF.text
                    break
            break
            
    # Captura dados do Cliente (Destinatário) e Localidade
    for dest in root.iter():
        if limpar_namespace(dest.tag) == 'dest':
            for sub in dest.iter():
                tag = limpar_namespace(sub.tag)
                if tag == 'xNome': cliente_nome = sub.text
                elif tag == 'xMun': cidade = sub.text
                elif tag == 'UF': uf = sub.text
                
    # Captura dados da Transportadora
    for transp in root.iter():
        if limpar_namespace(transp.tag) == 'transporta':
            for sub in transp.iter():
                if limpar_namespace(sub.tag) == 'xNome':
                    transportadora = sub.text
                    break
            break
            
    # Captura os produtos da nota
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
            
    infos_nota = {
        "numero_nota": numero_nota,
        "cliente": cliente_nome,
        "cidade": cidade,
        "uf": uf,
        "transportadora": transportadora
    }
            
    return pd.DataFrame(produtos), infos_nota

# 3. Gerador de PDF incluindo os dados do cliente e transportadora
def gerar_pdf(df, infos, valor_liq_total, icms_total):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    # Cabeçalho
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, "SISTEMA DE PRÉ-NOTA DE DEVOLUÇÃO", ln=True, align='C')
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, f"Nota Fiscal de Origem Nº: {infos['numero_nota']}", ln=True, align='C')
    pdf.ln(3)
    
    # Bloco de Informações (Cliente, Destino e Transportadora)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(0, 5, f"Cliente: {infos['cliente'][:50]}", ln=True)
    pdf.cell(0, 5, f"Destino: {infos['cidade']} - {infos['uf']} | Transportadora: {infos['transportadora']}", ln=True)
    pdf.ln(4)
    
    # Tabela de Itens
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

nf_origem = st.file_uploader("Anexe o XML da Nota Fiscal de Origem", type=["xml"])

if nf_origem:
    df_produtos, infos_nota = processar_xml_nf(nf_origem)
    
    st.success("Documento processado com sucesso!")
    
    # Exibindo dados organizados na tela
    st.markdown(f"#### Nota Fiscal Nº `{infos_nota['numero_nota']}`")
    st.info(f"**Cliente:** {infos_nota['cliente']} \n\n **Destino:** {infos_nota['cidade']} - {infos_nota['uf']} | **Transportadora:** {infos_nota['transportadora']}")
    
    st.write("Insira as quantidades dos itens que retornarão ao estoque:")
    
    espelho_itens = []
    valor_liquido_total = 0.0
    icms_normal_total = 0.0
    quantidade_total_pecas = 0.0
    
    with st.container():
        for index, linha in df_produtos.iterrows():
            nome = linha['Nome']
            qtd_orig = linha['Qtd Original']
            v_unit = linha['Valor Unitário']
            v_base_orig = linha['Valor Base']
            icms_orig = linha['ICMS Original']
            desconto_orig = linha['Desconto']
            
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
                quantidade_total_pecas += qtd_dev  # Soma correta do volume total de unidades
                
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
            st.metric(label="Volume Total de Unidades", value=int(quantidade_total_pecas))
        with col_t2:
            st.metric(label="Total de ICMS Calculado", value=f"R$ {icms_normal_total:.2f}")
        with col_t3:
            st.metric(label="VALOR LÍQUIDO TOTAL", value=f"R$ {valor_liquido_total:.2f}")
        
        st.markdown("---")
        
        pdf_pronto = gerar_pdf(df_final, infos_nota, valor_liquido_total, icms_normal_total)
        st.download_button(
            label="📄 Emitir Pré-Nota em PDF",
            data=pdf_pronto,
            file_name=f"Pre_Nota_Devolucao_{infos_nota['numero_nota']}.pdf",
            mime="application/pdf",
            type="primary"
        )
