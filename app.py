import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
from fpdf import FPDF
import tempfile
from datetime import datetime
import os

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
# 2. CONTROLE AUTOMÁTICO DE HISTÓRICO (CSV)
# -------------------------------------------------------------------------
ARQUIVO_HISTORICO = "historico_notas.csv"

def registrar_nota_automaticamente(numero_nota, data_emissao_xml, operador):
    if not os.path.exists(ARQUIVO_HISTORICO):
        df_hist = pd.DataFrame(columns=["Nota", "Data", "Operador", "Ano", "Mês"])
        df_hist.to_csv(ARQUIVO_HISTORICO, index=False)
    
    df_hist = pd.read_csv(ARQUIVO_HISTORICO)
    
    # Evita duplicar se a mesma nota já foi registrada antes
    if str(numero_nota) not in df_hist["Nota"].astype(str).values:
        data_obj = datetime.strptime(data_emissao_xml[:10], "%Y-%m-%d")
        novo = pd.DataFrame([{
            "Nota": str(numero_nota),
            "Data": data_obj.strftime("%Y-%m-%d"),
            "Operador": operador,
            "Ano": data_obj.strftime("%Y"),
            "Mês": data_obj.strftime("%Y-%m")
        }])
        df_hist = pd.concat([df_hist, novo], ignore_index=True)
        df_hist.to_csv(ARQUIVO_HISTORICO, index=False)

# -------------------------------------------------------------------------
# 3. LÓGICA DE LEITURA DO XML (COM DATA E IPI)
# -------------------------------------------------------------------------

def limpar_namespace(tag):
    return tag.split('}')[-1] if '}' in tag else tag

def processar_unico_xml(arquivo_xml):
    tree = ET.parse(arquivo_xml)
    root = tree.getroot()
    
    numero_nota = "Não encontrado"
    data_emissao = datetime.now().strftime("%Y-%m-%d")
    cliente_nome = "Não informado"
    cidade = ""
    uf = ""
    transportadora = "Não informada"
    produtos = []
    
    for ide in root.iter():
        if limpar_namespace(ide.tag) == 'ide':
            for sub in ide.iter():
                tag = limpar_namespace(sub.tag)
                if tag == 'nNF':
                    numero_nota = sub.text
                elif tag == 'dhEmi':
                    data_emissao = sub.text
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
        "data_emissao": data_emissao,
        "cliente": cliente_nome,
        "cidade": cidade,
        "uf": uf,
        "transportadora": transportadora
    }
            
    return pd.DataFrame(produtos), infos_nota

# -------------------------------------------------------------------------
# 4. GERADOR DE PDF INDIVIDUAL
# -------------------------------------------------------------------------

def gerar_pdf(df, infos, valor_liq_total, icms_total, ipi_total, data_geracao, usuario_gerador):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, "LABORATÓRIO GROSS S/A - PRÉ-NOTA DE DEVOLUÇÃO", ln=True, align='C')
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, f"Nota Fiscal de Origem Nº: {infos['numero_nota']}", ln=True, align='C')
    pdf.set_font("Arial", size=8)
    pdf.cell(0, 5, f"Data de Emissão: {data_geracao}", ln=True, align='C')
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
    pdf.cell(0, 4, f"Data de Emissao: {data_geracao} | Operador: {usuario_gerador}", ln=True)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        with open(tmp.name, "rb") as f:
            return f.read()

# ---------------------------------------------------------
# 5. INTERFACE PRINCIPAL
# ---------------------------------------------------------

st.set_page_config(page_title="Emissão e Histórico - Gross", layout="wide")

col_title, col_logout = st.columns([6, 1])
with col_title:
    st.title("📄 Sistema de Pré-Notas e Contador Automático - Gross")
with col_logout:
    st.write(f"👤 *{st.session_state.usuario_email}*")
    if st.button("🚪 Sair"):
        st.session_state.autenticado = False
        st.rerun()

st.markdown("---")

# Abas para separar a emissão do painel de contagem
aba_emissao, aba_relatorios = st.tabs(["Emissão de Pré-Notas", "📊 Histórico e Contador Automático"])

with aba_emissao:
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
                    
                    # Salva automaticamente no contador de notas ao emitir o PDF
                    registrar_nota_automaticamente(infos_nota['numero_nota'], infos_nota['data_emissao'], st.session_state.usuario_email)
                    
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

with aba_relatorios:
    st.subheader("📈 Painel de Controle e Contagem Automática")
    
    if os.path.exists(ARQUIVO_HISTORICO):
        df_hist = pd.read_csv(ARQUIVO_HISTORICO)
        
        if not df_hist.empty:
            tab_d, tab_m, tab_a, tab_g = st.tabs(["Visão Diária", "Visão Mensal", "Visão Anual", "Notas Registradas"])
            
            with tab_d:
                st.markdown("### Quantidade de Notas por Dia")
                df_dia = df_hist.groupby("Data")["Nota"].count().reset_index().rename(columns={"Nota": "Total de Notas"})
                st.dataframe(df_dia, use_container_width=True)
                st.bar_chart(df_dia.set_index("Data"))
                
            with tab_m:
                st.markdown("### Quantidade de Notas por Mês")
                df_mes = df_hist.groupby("Mês")["Nota"].count().reset_index().rename(columns={"Nota": "Total de Notas"})
                st.dataframe(df_mes, use_container_width=True)
                st.bar_chart(df_mes.set_index("Mês"))
                
            with tab_a:
                st.markdown("### Quantidade de Notas por Ano")
                df_ano = df_hist.groupby("Ano")["Nota"].count().reset_index().rename(columns={"Nota": "Total de Notas"})
                st.dataframe(df_ano, use_container_width=True)
                st.bar_chart(df_ano.set_index("Ano"))
                
            with tab_g:
                st.markdown("### Histórico Completo de Notas Emitidas")
                st.dataframe(df_hist, use_container_width=True)
        else:
            st.info("Nenhuma nota gerada automaticamente ainda. Faça o download de uma pré-nota na aba anterior para registrar.")
    else:
        st.info("O histórico está vazio. As notas serão contabilizadas automaticamente assim que você emitir as primeiras pré-notas.")
