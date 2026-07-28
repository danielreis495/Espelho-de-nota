import streamlit as st
import xml.etree.ElementTree as ET
import pandas as pd
from fpdf import FPDF
import tempfile

# 1. Função para remover as tags complexas do XML
def limpar_namespace(tag):
    return tag.split('}')[-1] if '}' in tag else tag

# 2. Leitor avançado: Captura descontos, ICMS-ST e Número da Nota
def processar_xml_nf(arquivo_xml):
    tree = ET.parse(arquivo_xml)
    root = tree.getroot()
    
    numero_nota = "Não encontrado"
    produtos = []
    
    # Raciocínio: Busca a seção de identificação (ide) e pega o número (nNF)
    for ide in root.iter():
        if limpar_namespace(ide.tag) == 'ide':
            for nNF in ide.iter():
                if limpar_namespace(nNF.tag) == 'nNF':
                    numero_nota = nNF.text
                    break
            break
            
    # Raciocínio: Vasculha os dados de preço e impostos do produto
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

# 3. Função para desenhar o arquivo PDF
def gerar_pdf(df, numero_nota):
    # Cria folha A4 em modo Paisagem (L)
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    # Raciocínio: Configura a fonte e escreve o título
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"CÁLCULO NOTA FISCAL - VENDA: {numero_nota}", ln=True, align='C')
    pdf.ln(5) # Pula linha
    
    # Raciocínio: Configura a largura das 13 colunas para caber na folha
    pdf.set_font("Arial", 'B', 7)
    larguras = [40, 12, 18, 18, 18, 15, 18, 22, 22, 18, 15, 20, 20]
    colunas = df.columns.tolist()
    
    # Imprime os cabeçalhos
    for i, col in enumerate(colunas):
        pdf.cell(larguras[i], 8, txt=str(col), border=1, align='C')
    pdf.ln()
    
    # Imprime os dados (linhas)
    pdf.set_font("Arial", size=7)
    for index, row in df.iterrows():
        for i, item in enumerate(row):
            # Limita caracteres de texto e formata números com 2 casas decimais
            texto = f"{item:.2f}" if isinstance(item, (int, float)) else str(item)[:22]
            pdf.cell(larguras[i], 8, txt=texto, border=1, align='C')
        pdf.ln()
    
    # Cria arquivo invisível e devolve os dados para download
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        with open(tmp.name, "rb") as f:
            return f.read()

# 4. Construção da Interface do Usuário
st.set_page_config(page_title="Gerador de Devolução NFe", layout="wide")
st.title("Espelho e Validador de NFD")

col1, col2 = st.columns(2)
with col1:
    nf_origem = st.file_uploader("1. Suba o XML da NF de Origem", type=["xml"])
with col2:
    nfd_devolucao = st.file_uploader("2. Suba o XML da NFD (Opcional)", type=["xml"])

if nf_origem:
    st.success("NF de Origem carregada com sucesso!")
    df_produtos, numero_nota = processar_xml_nf(nf_origem)
    
    st.markdown(f"### Número da Nota: **{numero_nota}**")
    st.markdown("### Selecione as Quantidades para o Espelho da Devolução")
    
    espelho_itens = []
    
    for index, linha in df_produtos.iterrows():
        nome = linha['Nome']
        qtd_orig = linha['Qtd Original']
        v_unit = linha['Valor Unitário']
        v_base_orig = linha['Valor Base']
        icms_orig = linha['ICMS Original']
        
        qtd_dev = st.number_input(f"{nome} (Máx: {qtd_orig})", min_value=0.0, max_value=float(qtd_orig), value=0.0, step=1.0)
        
        if qtd_dev > 0:
            fator_proporcao = qtd_dev / qtd_orig
            valor_item_dev = qtd_dev * v_unit
            icms_item_dev = icms_orig * fator_proporcao
            
            # Simulando regras contábeis básicas para preencher o layout desejado
            repasse = valor_item_dev * 0.8925
            desc = repasse * 0.08
            vl_liq = repasse - desc
            
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

    # 5. Exibição dos Resultados e Botão de Download
    if espelho_itens:
        df_final = pd.DataFrame(espelho_itens)
        
        st.markdown("---")
        st.subheader("Resumo do Espelho de Devolução")
        
        # Exibe a tabela replicando a estrutura da planilha Excel
        st.dataframe(df_final, use_container_width=True)
        
        # Gera o botão e aciona o motor de PDF
        pdf_pronto = gerar_pdf(df_final, numero_nota)
        st.download_button(
            label="📄 Gerar PDF da Nota",
            data=pdf_pronto,
            file_name=f"Calculo_NF_{numero_nota}.pdf",
            mime="application/pdf"
        )
