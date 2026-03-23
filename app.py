from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st

from api_client import ApiClient, ApiError
from certificado_generator import build_certificado_pdf, build_certificados_zip, template_exists_for_orgao
from utils import (
    empty_lote_template_bytes,
    ensure_iso_date_string,
    format_carga_horaria_display,
    format_date_br,
    get_public_course_date_bounds,
    mask_cpf,
    normalize_cpf,
    parse_carga_horaria_input,
    parse_date_like,
    records_to_dataframe,
)

st.set_page_config(page_title="Certificados", page_icon="📄", layout="wide")

API_URL = st.secrets["API_URL"]
API_TOKEN = st.secrets["API_TOKEN"]


def get_api_client() -> ApiClient:
    return ApiClient(api_url=API_URL, api_token=API_TOKEN)


def init_session_state() -> None:
    defaults = {
        "authenticated": False,
        "session_token": "",
        "login": "",
        "orgaos": [],
        "expira_em": "",
        "curso_editando": None,
        "certificado_editando": None,
        "show_new_course_form": False,
        "show_new_cert_form": False,
        "public_certificados_por_cpf": [],
        "public_validated_cert": None,
        "curso_busca": "",
        "curso_filtro_orgao": "",
        "curso_filtro_ativo": "Ativos",
        "curso_busca_executada": False,
        "cert_busca": "",
        "cert_filtro_curso": "",
        "cert_filtro_ativo": "Ativos",
        "cert_busca_executada": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def logout() -> None:
    client = get_api_client()
    token = st.session_state.get("session_token", "")
    if token:
        try:
            client.logout(token)
        except Exception:
            pass

    st.session_state["authenticated"] = False
    st.session_state["session_token"] = ""
    st.session_state["login"] = ""
    st.session_state["orgaos"] = []
    st.session_state["expira_em"] = ""
    st.session_state["curso_editando"] = None
    st.session_state["certificado_editando"] = None
    st.session_state["show_new_course_form"] = False
    st.session_state["show_new_cert_form"] = False


def perform_login(login: str, senha: str) -> None:
    client = get_api_client()
    result = client.login(login=login, senha=senha)
    st.session_state["authenticated"] = True
    st.session_state["session_token"] = result["session_token"]
    st.session_state["login"] = result["login"]
    st.session_state["orgaos"] = result["orgaos"]
    st.session_state["expira_em"] = result["expira_em"]
    st.rerun()


def public_login_area() -> None:
    st.subheader("Login")
    with st.form("login_form"):
        login = st.text_input("Login")
        senha = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar", use_container_width=True)
        if submitted:
            try:
                perform_login(login, senha)
            except ApiError as exc:
                st.error(str(exc))


def public_download_area() -> None:
    st.subheader("Baixar meu(s) certificado(s)")
    cpf = st.text_input("CPF", key="public_cpf_search", placeholder="Somente números ou com máscara")
    buscar = st.button("Buscar certificados", key="btn_buscar_cpf", use_container_width=True)

    if buscar:
        try:
            client = get_api_client()
            response = client.buscar_certificados_por_cpf(cpf)
            st.session_state["public_certificados_por_cpf"] = response.get("registros", [])
            st.session_state["public_certificados_cpf_mascarado"] = response.get("cpf_mascarado", mask_cpf(cpf))
        except ApiError as exc:
            st.error(str(exc))
            st.session_state["public_certificados_por_cpf"] = []

    registros = st.session_state.get("public_certificados_por_cpf", [])
    if registros:
        tabela = []
        for reg in registros:
            tabela.append({
                "Código": reg.get("cod_validacao", ""),
                "Curso": reg.get("curso_nome", ""),
                "Órgão": reg.get("orgao_nome", ""),
                "Conclusão": format_date_br(reg.get("conclusao", "")),
                "Carga horária": format_carga_horaria_display(reg.get("carga_horaria", "")),
            })

        st.success(
            f"{len(registros)} certificado(s) localizado(s) para "
            f"{st.session_state.get('public_certificados_cpf_mascarado', '')}."
        )
        st.dataframe(pd.DataFrame(tabela), use_container_width=True, hide_index=True)

        try:
            zip_bytes = build_certificados_zip(registros)
            st.download_button(
                "Baixar todos (ZIP)",
                data=zip_bytes,
                file_name=f"certificados_{normalize_cpf(cpf)}.zip",
                mime="application/zip",
                use_container_width=True,
            )
        except FileNotFoundError as exc:
            st.warning(str(exc))


        st.markdown("Downloads individuais")
        for reg in registros:
            template_ok = template_exists_for_orgao(reg.get("orgao", ""))
            cols = st.columns([4, 2, 2])
            with cols[0]:
                st.write(f"{reg.get('curso_nome', '')} — {format_date_br(reg.get('conclusao', ''))}")
            with cols[1]:
                st.write(reg.get("cod_validacao", ""))
            with cols[2]:
                if template_ok:
                    try:
                        pdf_bytes = build_certificado_pdf(reg)
                        st.download_button(
                            "Baixar",
                            data=pdf_bytes,
                            file_name=f"{reg.get('cod_validacao', 'certificado')}.pdf",
                            mime="application/pdf",
                            key=f"download_single_{reg.get('cod_validacao', '')}",
                            use_container_width=True,
                        )
                    except Exception as exc:
                        st.error(f"Falha ao gerar PDF: {exc}")
                else:
                    st.caption("Template do órgão não localizado.")


def public_validate_area() -> None:
    st.subheader("Validar certificado")
    cod_validacao = st.text_input("Código de validação", key="public_validation_code")
    validar = st.button("Validar", key="btn_validar_cert", use_container_width=True)

    if validar:
        if not cod_validacao.strip():
            st.session_state["public_validated_cert"] = None
            st.error("Informe o código de validação.")
        else:
            try:
                client = get_api_client()
                result = client.validar_certificado(cod_validacao)
                st.session_state["public_validated_cert"] = result["certificado"]
            except ApiError as exc:
                st.session_state["public_validated_cert"] = None
                st.error(str(exc))

    cert = st.session_state.get("public_validated_cert")
    if cert:
        st.text_input("Curso", value=cert.get("curso_nome", ""), disabled=True)
        st.text_input("Órgão", value=cert.get("orgao_nome", ""), disabled=True)
        st.text_input("Nome", value=cert.get("nome", ""), disabled=True)
        st.text_input("CPF", value=cert.get("cpf_mascarado", ""), disabled=True)
        st.text_input("Carga horária", value=format_carga_horaria_display(cert.get("carga_horaria", "")), disabled=True)
        st.text_input("Conclusão", value=format_date_br(cert.get("conclusao", "")), disabled=True)
        st.text_input("Código", value=cert.get("cod_validacao", ""), disabled=True)
        st.text_area("Ementa", value=cert.get("ementa", ""), height=180, disabled=True)


def render_public_home() -> None:
    st.title("Certificados")

    with st.container():
        public_download_area()

    st.markdown("---")

    with st.container():
        public_validate_area()

    st.markdown("---")

    with st.container():
        public_login_area()


def render_auth_header() -> None:
    st.title("Gestão de Certificados")
    left, right = st.columns([4, 1])
    with left:
        st.caption(
            f"Usuário: {st.session_state.get('login', '')} | "
            f"Órgãos: {', '.join(st.session_state.get('orgaos', []))} | "
            f"Sessão até: {st.session_state.get('expira_em', '')}"
        )
    with right:
        st.button("Sair", on_click=logout, use_container_width=True)


def load_orgaos(client: ApiClient) -> list[dict[str, Any]]:
    return client.listar_orgaos(st.session_state["session_token"]).get("orgaos", [])


def load_cursos(client: ApiClient, busca: str = "", orgao: str = "", ativo: bool | None = True) -> list[dict[str, Any]]:
    return client.listar_cursos(
        st.session_state["session_token"],
        busca=busca or None,
        orgao=orgao or None,
        ativo=ativo,
    ).get("cursos", [])


def load_certificados(
    client: ApiClient,
    busca: str = "",
    curso: str = "",
    ativo: bool | None = True,
    data_inicio: str | None = None,
    data_fim: str | None = None,
) -> list[dict[str, Any]]:
    return client.listar_certificados(
        st.session_state["session_token"],
        busca=busca or None,
        curso=curso or None,
        ativo=ativo,
        data_inicio=data_inicio,
        data_fim=data_fim,
    ).get("certificados", [])


def select_orgao_widget(orgaos: list[dict[str, Any]], current_value: str = "", key: str = "orgao_select") -> str:
    options = [o["id_orgao"] for o in orgaos]
    labels = {o["id_orgao"]: o["nome_orgao"] for o in orgaos}
    if current_value and current_value not in options:
        options = [current_value] + options
        labels[current_value] = current_value
    idx = options.index(current_value) if current_value in options else 0
    return st.selectbox(
        "Órgão",
        options=options,
        index=idx if options else None,
        format_func=lambda x: labels.get(x, x),
        key=key,
    )


def select_curso_widget(cursos: list[dict[str, Any]], current_value: str = "", key: str = "curso_select") -> str:
    options = [c["id_curso"] for c in cursos if c.get("ativo", True)]
    if current_value and current_value not in options:
        options = [current_value] + options

    labels = {c["id_curso"]: f'{c["nome"]} | {c["orgao_nome"]} | {format_date_br(c["conclusao"])}' for c in cursos}
    idx = options.index(current_value) if current_value in options else 0
    return st.selectbox(
        "Curso",
        options=options,
        index=idx if options else None,
        format_func=lambda x: labels.get(x, x),
        key=key,
    )


def render_cursos_tab(client: ApiClient) -> None:
    st.subheader("Cursos")
    orgaos = load_orgaos(client)

    ativo_map = {"Ativos": True, "Inativos": False, "Todos": None}

    c1, c2, c3 = st.columns([4, 6, 2])

    with c1:
        orgao_opts = [""] + [o["id_orgao"] for o in orgaos]
        labels_orgaos = {"": "Selecione um órgão"} | {o["id_orgao"]: o["nome_orgao"] for o in orgaos}
        filtro_orgao = st.selectbox(
            "Filtrar por órgão",
            options=orgao_opts,
            format_func=lambda x: labels_orgaos.get(x, x),
            key="curso_filtro_orgao",
        )

    with c2:
        cursos_dropdown = []
        if filtro_orgao:
            cursos_dropdown = load_cursos(client, orgao=filtro_orgao, ativo=ativo_map.get(st.session_state.get("curso_filtro_ativo", "Ativos")))

        curso_opts = [""] + [c["id_curso"] for c in cursos_dropdown]
        labels_cursos = {"": "Selecione um curso"} | {
            c["id_curso"]: f'{c["nome"]} | {format_date_br(c["conclusao"])}'
            for c in cursos_dropdown
        }

        filtro_curso = st.selectbox(
            "Curso",
            options=curso_opts,
            format_func=lambda x: labels_cursos.get(x, x),
            key="curso_filtro_curso",
            disabled=not filtro_orgao,
        )

    with c3:
        ativo_opt = st.selectbox(
            "Ativo",
            options=["Ativos", "Inativos", "Todos"],
            key="curso_filtro_ativo",
        )

    if st.button("Buscar", key="curso_buscar_btn", use_container_width=True):
        st.session_state["curso_busca_executada"] = True
        st.rerun()

    if st.button("Novo curso", key="novo_curso_btn", use_container_width=True):
        st.session_state["show_new_course_form"] = True
        st.session_state["curso_editando"] = None

    cursos: list[dict[str, Any]] = []
    if st.session_state.get("curso_busca_executada") and filtro_curso:
        cursos = [c for c in cursos_dropdown if c["id_curso"] == filtro_curso]

    if not st.session_state.get("curso_busca_executada"):
        st.info("A tabela começa vazia. Selecione um órgão, escolha um curso e clique em Buscar.")
    elif not filtro_orgao:
        st.info("Selecione um órgão para carregar os cursos.")
    elif not filtro_curso:
        st.info("Selecione um curso para carregar os dados.")
    elif cursos:
        tabela = []
        for curso in cursos:
            tabela.append({
                "ID": curso["id_curso"],
                "Nome": curso["nome"],
                "Conclusão": format_date_br(curso["conclusao"]),
                "Carga horária": format_carga_horaria_display(curso["carga_horaria"]),
                "Órgão": curso["orgao_nome"],
                "Ativo": curso["ativo"],
            })

        st.dataframe(pd.DataFrame(tabela), use_container_width=True, hide_index=True)

        st.markdown("Ações")
        for curso in cursos:
            a, b, c, d = st.columns([4, 2, 1, 1])
            with a:
                st.write(f'{curso["nome"]} — {curso["orgao_nome"]}')
            with b:
                st.write(f'Conclusão: {format_date_br(curso["conclusao"])}')
            with c:
                if st.button("Editar", key=f'edit_curso_{curso["id_curso"]}', use_container_width=True):
                    st.session_state["curso_editando"] = curso
                    st.session_state["show_new_course_form"] = False
            with d:
                if curso.get("ativo", True):
                    if st.button("Excluir", key=f'delete_curso_{curso["id_curso"]}', use_container_width=True):
                        try:
                            client.excluir_curso(st.session_state["session_token"], curso["id_curso"])
                            st.success("Curso desativado.")
                            st.rerun()
                        except ApiError as exc:
                            st.error(str(exc))
    else:
        st.info("Nenhum curso encontrado para o filtro informado.")

    current = st.session_state.get("curso_editando") or {}
    show_form = st.session_state.get("show_new_course_form", False) or bool(current)
    if show_form:
        is_edit = bool(current)
        st.markdown("---")
        st.subheader("Editar curso" if is_edit else "Novo curso")
        with st.form("curso_form"):
            nome = st.text_input("Nome", value=current.get("nome", ""))
            conclusao_val = parse_date_like(current.get("conclusao", "")) or date.today()
            conclusao = st.date_input("Conclusão", value=conclusao_val, format="DD/MM/YYYY")
            carga_horaria_texto = st.text_input(
                "Carga horária",
                value=format_carga_horaria_display(current.get("carga_horaria", "")),
                help="Informe números inteiros ou decimais. Exemplos: 20 ou 20,5",
            )
            ementa = st.text_area("Ementa", value=current.get("ementa", ""), height=180)
            orgao = select_orgao_widget(orgaos, current.get("orgao", ""), key="curso_form_orgao")
            save = st.form_submit_button("Salvar curso", use_container_width=True)
            cancel = st.form_submit_button("Cancelar", use_container_width=True)

            if cancel:
                st.session_state["curso_editando"] = None
                st.session_state["show_new_course_form"] = False
                st.rerun()

            if save:
                try:
                    carga_horaria = parse_carga_horaria_input(carga_horaria_texto)
                    if is_edit:
                        client.editar_curso(
                            st.session_state["session_token"],
                            id_curso=current["id_curso"],
                            nome=nome,
                            conclusao=ensure_iso_date_string(conclusao),
                            carga_horaria=carga_horaria,
                            ementa=ementa,
                            orgao=orgao,
                        )
                        st.success("Curso atualizado com sucesso.")
                    else:
                        client.criar_curso(
                            st.session_state["session_token"],
                            nome=nome,
                            conclusao=ensure_iso_date_string(conclusao),
                            carga_horaria=carga_horaria,
                            ementa=ementa,
                            orgao=orgao,
                        )
                        st.success("Curso criado com sucesso.")
                    st.session_state["curso_editando"] = None
                    st.session_state["show_new_course_form"] = False
                    st.rerun()
                except (ApiError, ValueError) as exc:
                    st.error(str(exc))

def read_lote_excel(uploaded_file) -> pd.DataFrame:
    try:
        return pd.read_excel(uploaded_file, dtype=str, engine="calamine")
    except Exception:
        uploaded_file.seek(0)
        return pd.read_excel(uploaded_file, dtype=str, engine="openpyxl")


def render_lote_section(client: ApiClient, cursos: list[dict[str, Any]]) -> None:
    st.markdown("---")
    st.subheader("Certificados em lote")

    template_bytes = empty_lote_template_bytes()
    st.download_button(
        "Certificados em lote - template",
        data=template_bytes,
        file_name="template_certificados_lote.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    curso_id = select_curso_widget(cursos, key="lote_curso_select")
    uploaded_file = st.file_uploader("Selecione a planilha XLSX", type=["xlsx"], key="lote_file_uploader")

    if st.button("Certificados em lote - criar", key="lote_criar_btn", use_container_width=True):
        if not uploaded_file:
            st.warning("Selecione um arquivo XLSX.")
            return
        try:
            df = read_lote_excel(uploaded_file)
            df.columns = [str(c).strip().lower() for c in df.columns]
            expected = {"nome", "cpf"}
            missing = expected - set(df.columns)
            if missing:
                st.error(f"Colunas ausentes: {', '.join(sorted(missing))}")
                return

            registros = []
            for _, row in df.iterrows():
                nome = str(row.get("nome", "") or "").strip()
                cpf = normalize_cpf(row.get("cpf", ""))
                if nome or cpf:
                    registros.append({"nome": nome, "cpf": cpf})

            response = client.criar_certificados_lote(st.session_state["session_token"], curso=curso_id, registros=registros)
            st.success(
                f'Concluído. Criados: {response.get("total_criado", 0)} | '
                f'Rejeitados: {response.get("total_rejeitado", 0)}'
            )
            erros = response.get("erros", [])
            if erros:
                st.dataframe(pd.DataFrame(erros), use_container_width=True, hide_index=True)
        except ApiError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(
                "Erro ao processar arquivo. "
                f"Detalhe: {exc}. "
                "Se persistir, instale também a biblioteca python-calamine."
            )


def render_certificados_tab(client: ApiClient) -> None:
    st.subheader("Certificados")
    cursos = load_cursos(client, ativo=True)

    c1, c2, c3, c4, c5, c6 = st.columns([3, 2, 2, 2, 1, 1])
    with c1:
        busca = st.text_input("Pesquisar por pessoa/CPF/curso", key="cert_busca")
    with c2:
        curso_options = [""] + [c["id_curso"] for c in cursos]
        curso_labels = {"": "Selecione um curso"} | {c["id_curso"]: f'{c["nome"]} | {c["orgao_nome"]}' for c in cursos}
        filtro_curso = st.selectbox("Filtrar por curso", options=curso_options, format_func=lambda x: curso_labels.get(x, x), key="cert_filtro_curso")
    min_dt, max_dt = get_public_course_date_bounds(cursos)
    with c3:
        data_inicio = st.date_input("Conclusão inicial", value=min_dt, key="cert_data_inicio", format="DD/MM/YYYY")
    with c4:
        data_fim = st.date_input("Conclusão final", value=max_dt, key="cert_data_fim", format="DD/MM/YYYY")
    with c5:
        if st.button("Buscar", key="cert_buscar_btn", use_container_width=True):
            st.session_state["cert_busca_executada"] = True
            st.rerun()
    with c6:
        if st.button("Limpar", key="cert_limpar_btn", use_container_width=True):
            st.session_state["cert_busca"] = ""
            st.session_state["cert_filtro_curso"] = ""
            st.session_state["cert_filtro_ativo"] = "Ativos"
            st.session_state["cert_busca_executada"] = False
            st.rerun()

    ativo_opt = st.selectbox("Ativo", options=["Ativos", "Inativos", "Todos"], key="cert_filtro_ativo")

    if st.button("Novo certificado", key="novo_cert_btn"):
        st.session_state["show_new_cert_form"] = True
        st.session_state["certificado_editando"] = None

    certificados: list[dict[str, Any]] = []
    if st.session_state.get("cert_busca_executada") and filtro_curso:
        ativo_map = {"Ativos": True, "Inativos": False, "Todos": None}
        certificados = load_certificados(
            client,
            busca=busca,
            curso=filtro_curso,
            ativo=ativo_map[ativo_opt],
            data_inicio=ensure_iso_date_string(data_inicio) if data_inicio else None,
            data_fim=ensure_iso_date_string(data_fim) if data_fim else None,
        )

    if not st.session_state.get("cert_busca_executada"):
        st.info("A tabela começa vazia. Selecione um curso e clique em Buscar.")
    elif not filtro_curso:
        st.info("Selecione um curso para carregar os certificados.")
    elif certificados:
        tabela = []
        for cert in certificados:
            tabela.append({
                "Nome": cert["nome"],
                "CPF": cert["cpf_mascarado"],
                "Curso": cert["curso_nome"],
                "Órgão": cert["orgao_nome"],
                "Conclusão": format_date_br(cert["conclusao"]),
                "Código": cert["cod_validacao"],
                "Ativo": cert["ativo"],
            })
        st.dataframe(pd.DataFrame(tabela), use_container_width=True, hide_index=True)

        st.markdown("Ações")
        for cert in certificados:
            a, b, c, d, e = st.columns([4, 2, 1, 1, 1])
            with a:
                st.write(f'{cert["nome"]} — {cert["curso_nome"]}')
            with b:
                st.write(cert["cpf_mascarado"])
            with c:
                if st.button("Editar", key=f'edit_cert_{cert["cod_validacao"]}', use_container_width=True):
                    st.session_state["certificado_editando"] = cert
                    st.session_state["show_new_cert_form"] = False
            with d:
                if cert.get("ativo", True):
                    if st.button("Excluir", key=f'delete_cert_{cert["cod_validacao"]}', use_container_width=True):
                        try:
                            client.excluir_certificado(st.session_state["session_token"], cert["cod_validacao"])
                            st.success("Certificado desativado.")
                            st.rerun()
                        except ApiError as exc:
                            st.error(str(exc))
            with e:
                if template_exists_for_orgao(cert.get("orgao", "")):
                    try:
                        pdf_bytes = build_certificado_pdf(cert)
                        st.download_button(
                            "PDF",
                            data=pdf_bytes,
                            file_name=f'{cert["cod_validacao"]}.pdf',
                            mime="application/pdf",
                            key=f'download_auth_{cert["cod_validacao"]}',
                            use_container_width=True,
                        )
                    except Exception as exc:
                        st.error(f"Falha PDF: {exc}")
                else:
                    st.caption("Sem template.")
    else:
        st.info("Nenhum certificado encontrado para o curso selecionado.")

    current = st.session_state.get("certificado_editando") or {}
    show_form = st.session_state.get("show_new_cert_form", False) or bool(current)
    if show_form:
        is_edit = bool(current)
        st.markdown("---")
        st.subheader("Editar certificado" if is_edit else "Novo certificado")
        with st.form("cert_form"):
            nome = st.text_input("Nome", value=current.get("nome", ""))
            cpf = st.text_input("CPF", value=current.get("cpf", "") or normalize_cpf(current.get("cpf_mascarado", "")))
            curso = select_curso_widget(cursos, current.get("curso", ""), key="cert_form_curso")
            save = st.form_submit_button("Salvar certificado", use_container_width=True)
            cancel = st.form_submit_button("Cancelar", use_container_width=True)

            if cancel:
                st.session_state["certificado_editando"] = None
                st.session_state["show_new_cert_form"] = False
                st.rerun()

            if save:
                try:
                    if is_edit:
                        client.editar_certificado(
                            st.session_state["session_token"],
                            cod_validacao=current["cod_validacao"],
                            nome=nome,
                            cpf=cpf,
                            curso=curso,
                        )
                        st.success("Certificado atualizado com sucesso.")
                    else:
                        client.criar_certificado(
                            st.session_state["session_token"],
                            nome=nome,
                            cpf=cpf,
                            curso=curso,
                        )
                        st.success("Certificado criado com sucesso.")
                    st.session_state["certificado_editando"] = None
                    st.session_state["show_new_cert_form"] = False
                    st.rerun()
                except ApiError as exc:
                    st.error(str(exc))

    render_lote_section(client, cursos)


def render_authenticated_home() -> None:
    render_auth_header()
    client = get_api_client()
    tab_cursos, tab_certificados = st.tabs(["Cursos", "Certificados"])
    with tab_cursos:
        render_cursos_tab(client)
    with tab_certificados:
        render_certificados_tab(client)


def main() -> None:
    init_session_state()
    if st.session_state["authenticated"]:
        render_authenticated_home()
    else:
        render_public_home()


if __name__ == "__main__":
    main()
