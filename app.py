import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
from fpdf import FPDF
import tempfile
from datetime import datetime

# -------------------------------------------------------------------------
# 1. SISTEMA DE LOGIN E AUTENTICAÇÃO POR E-MAIL E SENHA
# -------------------------------------------------------------------------

USUARIOS_AUTORIZADOS = {
    "daniel.reis@gross.com.br": "gross2026",
    "operacional@gross.com.br": "gross123",
    "fiscal@gross.com.br": "nfe2026"
}

def verificar_autenticacao():
    if 'autenticado' not in st.session_state:
        st.session_state.autenticado = False
        st.session_state.usuario_email = ""

    if not st.session_state.autenticado:
        st.set_page_config(page_title="Login - Laboratório Gross", layout="centered")
        st.title("🔒 Laboratório Gross - Acesso Restrito")
        st.markdown("Insira seu e-mail corporativo e senha para acessar o sistema de pré-notas.")
        
        email_input = st.text_input("E-mail corporativo")
        senha_input = st.text_input("Senha", type="password")
        
        if st.button("Entrar", type="primary"):
            if email_input in USUARIOS_AUTORIZADOS and USUARIOS_AUTORIZADOS[email_input] == senha_input:
                st.session_state.autenticado = True
                st.session_state.usuario_email = email_input
                st.rerun()
            else:
                st.error("E-mail ou senha incorretos. Verifique seus dados.")
        return False
    return True

if not verificar_autenticacao():
    st.stop()

# -------------------------------------------------------------------------
# 2. LÓGICA DE LEITURA INDIVIDUAL DE CADA XML (COM CAPTURA DE IPI)
# -------------------------------------------------------------------------

def limpar_namespace(tag):
    return tag.split('}')[-1] if '}' in tag else tag

def processar_unico_xml(arquivo_xml):
    tree = ET.parse(arquivo_xml)
    root = tree.getroot()
    
    numero_nota = "Não encontrado"
    cliente_nome = "Não informado"
    cidade = ""
    uf = ""
    transportadora = "Não informada"
    produtos = []
    
    for ide in root.iter():
        if limpar_namespace(ide.tag) == 'ide':
            for nNF in ide.iter():
                if limpar_namespace(nNF.tag) == 'nNF':
                    numero_nota = nNF.text
                    break
            break
            
    for dest in root.iter():
        if limpar_namespace(dest.tag) == 'dest':
            for sub in dest.iter():
                tag = limpar_namespace(sub.tag)
                if tag == 'xNome': cliente_nome = sub.text
                elif tag == 'xMun': cidade = sub.text
                elif tag == 'UF': uf = sub.text
                
    for transp in root.iter():
        if limpar_namespace(transp.tag) == 'transporta':
            for sub in transp.iter():
                if limpar_namespace(sub.tag) == 'xNome':
                    transportadora = sub.text
                    break
            break
            
    for det in root.iter():
        if limpar_namespace(det.tag) == 'det':
            prod_info = {
                'Nome': '', 'Qtd Original': 0.0, 'Valor Unitário': 0.0, 
                'Valor Total Item': 0.0, 'Desconto': 0.0, 'ICMS Original': 0.0, 'IPI Original': 0.0
            }
            
            for prod in det.iter():
                tag = limpar_namespace(prod.tag)
                if tag == 'xProd': prod_info['Nome'] = prod.text
                elif tag == 'qCom': prod_info['Qtd Original'] = float(prod.text)
                elif tag == 'vUnCom': prod_info['Valor Unitário'] = float(prod.text)
                elif tag == 'vProd': prod_info['Valor Total Item'] = float(prod.text)
                elif tag == 'vDesc': prod_info['Desconto'] = float(prod.text)
            
            # Captura ICMS e IPI específicos do item
            for imposto in det.iter():
                tag = limpar_namespace(imposto.tag)
                if tag == 'vICMS':
                    prod_info['ICMS Original'] += float(imposto.text)
                elif tag == 'vIPI':
                    prod_info['IPI Original'] += float(imposto.text)
            
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

# -------------------------------------------------------------------------
# 3. GERADOR DE PDF INDIVIDUAL
# -------------------------------------------------------------------------

def gerar_pdf(df, infos, valor_liq_total, icms_total, ipi_total, data_emissao, usuario_gerador):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, "LABORATÓRIO GROSS S/A - PRÉ-NOTA DE DEVOLUÇÃO", ln=True, align='C')
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, f"Nota Fiscal de Origem Nº: {infos['numero_nota']}", ln=True, align='C')
    pdf.set_font("Arial", size=8)
    pdf.cell(0, 5, f"Data de Emissão: {data_emissao}", ln=True, align='C')
    pdf.ln(3)
    
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(0, 5, f"Cliente: {infos['cliente'][:50]}", ln=True)
    pdf.cell(0, 5, f"Destino: {infos['cidade']} - {infos['uf']} | Transportadora: {infos['transportadora']}", ln=True)
    pdf.ln(4)
    
    pdf.set_font("Arial", 'B', 8)
    larguras = [65, 12, 22, 25, 25, 22, 22, 25, 22, 17]
    colunas = df.columns.tolist()
    
    pdf.set_fill_color(240, 240, 240)
    for i, col in enumerate(colunas):
        pdf.cell(larguras[i], 7, txt=str(col), border=1, align='C', fill=True)
    pdf.ln()
    
    pdf.set_font("Arial", size=8)
    for index, row in df.iterrows():
        for i, item in enumerate(row):
            texto = f"{item:.2f}" if isinstance(item, (int, float)) else str(item)[:30]
            pdf.cell(larguras[i], 6, txt=texto, border=1, align='C')
        pdf.ln()
        
    pdf.ln(4)
    
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(0, 6, "TOTAIS DA DEVOLUÇÃO:", ln=True)
    pdf.set_font("Arial", size=9)
    pdf.cell(0, 6, f"Total de ICMS Calculado: R$ {icms_total:.2f}", ln=True)
    pdf.cell(0, 6, f"Total de IPI Calculado: R$ {ipi_total:.2f}", ln=True)
    pdf.cell(0, 6, f"VALOR LÍQUIDO TOTAL DA DEVOLUÇÃO (Com IPI): R$ {valor_liq_total:.2f}", ln=True)
    pdf.ln(4)
    
    pdf.set_draw_color(0, 51, 102)
    pdf.set_fill_color(245, 247, 250)
    pdf.rect(10, pdf.get_y(), 277, 22, style='DF')
    
    pdf.set_xy(12, pdf.get_y() + 2)
    pdf.set_font("Arial", 'B', 9)
    pdf.set_text_color(0, 51, 102)
    pdf.cell(0, 5, "LABORATORIO GROSS S/A - DOCUMENTO AUTENTICADO", ln=True)
    
    pdf.set_x(12)
    pdf.set_font("Arial", size=8)
    pdf.set_text_color(50, 50, 50)
    pdf.cell(0, 4, f"Emitido e validado eletronicamente pelo sistema interno.", ln=True)
    pdf.set_x(12)
    pdf.cell(0, 4, f"Data de Emissao: {data_emissao} | Operador: {usuario_gerador}", ln=True)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        with open(tmp.name, "rb") as f:
            return f.read()

# -------------------------------------------------------------------------
# 4. INTERFACE PRINCIPAL DO APLICATIVO
# -------------------------------------------------------------------------

st.set_page_config(page_title="Emissão de Devolução - Gross", layout="wide")

col_title, col_logout = st.columns([6, 1])
with col_title:
    st.title("📄 Sistema de Pré-Nota de Devolução - Gross")
with col_logout:
    st.write(f"👤 *{st.session_state.usuario_email}*")
    if st.button("🚪 Sair"):
        st.session_state.autenticado = False
        st.rerun()

st.markdown("---")

arquivos_origem = st.file_uploader("Anexe um ou mais arquivos XML das Notas Fiscais de Origem", type=["xml"], accept_multiple_files=True)

if arquivos_origem:
    data_atual = datetime.now().strftime("%d/%m/%Y")
    data_hora_completa = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    
    st.success(f"{len(arquivos_origem)} arquivo(s) XML carregado(s) com sucesso!")
    st.write("Configure abaixo os itens de devolução para cada nota processada:")

    for idx, arquivo in enumerate(arquivos_origem):
        df_produtos, infos_nota = processar_unico_xml(arquivo)
        
        with st.expander(f"📦 Nota Fiscal Nº {infos_nota['numero_nota']} - Cliente: {infos_nota['cliente']}", expanded=True):
            st.markdown(f"**Destino:** {infos_nota['cidade']} - {infos_nota['uf']} | **Transportadora:** {infos_nota['transportadora']}")
            
            espelho_itens = []
            valor_liquido_total = 0.0
            icms_normal_total = 0.0
            ipi_total = 0.0
            quantidade_total_pecas = 0.0
            
            for index, linha in df_produtos.iterrows():
                nome = linha['Nome']
                qtd_orig = linha['Qtd Original']
                v_unit = linha['Valor Unitário']
                v_base_orig = linha['Valor Base']
                icms_orig = linha['ICMS Original']
                ipi_orig = linha['IPI Original']
                desconto_orig = linha['Desconto']
                
                qtd_dev = st.number_input(
                    f"Item: {nome} (Qtd. na NF: {int(qtd_orig)})", 
                    min_value=0.0, 
                    max_value=float(qtd_orig), 
                    value=0.0, 
                    step=1.0,
                    format="%.0f",
                    key=f"nota_{idx}_item_{index}"
                )
                
                if qtd_dev > 0:
                    fator_proporcao = qtd_dev / qtd_orig
                    valor_item_dev = qtd_dev * v_unit
                    icms_item_dev = icms_orig * fator_proporcao
                    ipi_item_dev = ipi_orig * fator_proporcao
                    desconto_item_dev = desconto_orig * fator_proporcao
                    
                    # Valor líquido do item agora incorpora o IPI proporcional
                    vl_liq_item = (valor_item_dev - desconto_item_dev) + ipi_item_dev
                    
                    valor_liquido_total += vl_liq_item
                    icms_normal_total += icms_item_dev
                    ipi_total += ipi_item_dev
                    quantidade_total_pecas += qtd_dev
                    
                    espelho_itens.append({
                        "PRODUTO": nome,
                        "QTE": qtd_dev,
                        "VL UNIT": v_unit,
                        "DESCONTO": desconto_item_dev,
                        "VL TOTAL": valor_item_dev,
                        "BASE ICMS": v_base_orig * fator_proporcao,
                        "ICMS": icms_item_dev,
                        "IPI": ipi_item_dev,
                        "VL LÍQUIDO": vl_liq_item
                    })

            if espelho_itens:
                df_final = pd.DataFrame(espelho_itens)
                
                st.markdown("---")
                st.markdown(f"**Resumo para a Nota {infos_nota['numero_nota']}**")
                st.dataframe(df_final.style.format(precision=2), use_container_width=True)
                
                col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                with col_m1:
                    st.metric(label="Total Unidades", value=int(quantidade_total_pecas))
                with col_m2:
                    st.metric(label="ICMS Calculado", value=f"R$ {icms_normal_total:.2f}")
                with col_m3:
                    st.metric(label="IPI Calculado", value=f"R$ {ipi_total:.2f}")
                with col_m4:
                    st.metric(label="VALOR LÍQUIDO", value=f"R$ {valor_liquido_total:.2f}")
                
                pdf_pronto = gerar_pdf(df_final, infos_nota, valor_liquido_total, icms_normal_total, ipi_total, data_atual, st.session_state.usuario_email)
                st.download_button(
                    label=f"📄 Baixar Pré-Nota da NF {infos_nota['numero_nota']}",
                    data=pdf_pronto,
                    file_name=f"Pre_Nota_Devolucao_{infos_nota['numero_nota']}.pdf",
                    mime="application/pdf",
                    key=f"btn_pdf_{idx}",
                    type="primary"
                )
            else:
                st.info("Insira a quantidade de pelo menos um item acima para liberar a pré-nota desta nota fiscal.")
