from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


class ApiError(Exception):
    pass


@dataclass
class ApiClient:
    api_url: str
    api_token: str
    timeout: int = 60

    def _post(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {"api_token": self.api_token, "action": action, **payload}
        try:
            response = requests.post(self.api_url, json=body, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ApiError(f"Falha de conexão com a API: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise ApiError(f"Resposta inválida da API: {response.text[:300]}") from exc

        if not data.get("success", False):
            raise ApiError(data.get("message", "Erro desconhecido da API."))

        return data

    def login(self, login: str, senha: str) -> dict[str, Any]:
        return self._post("login", {"login": login, "senha": senha})

    def logout(self, session_token: str) -> dict[str, Any]:
        return self._post("logout", {"session_token": session_token})

    def validar_certificado(self, cod_validacao: str) -> dict[str, Any]:
        return self._post("validar_certificado", {"cod_validacao": cod_validacao})

    def buscar_certificados_por_cpf(self, cpf: str) -> dict[str, Any]:
        return self._post("buscar_certificados_por_cpf", {"cpf": cpf})

    def listar_orgaos(self, session_token: str) -> dict[str, Any]:
        return self._post("listar_orgaos", {"session_token": session_token})

    def listar_cursos(self, session_token: str, busca: str | None = None, orgao: str | None = None, ativo: bool | None = True) -> dict[str, Any]:
        payload = {"session_token": session_token}
        if busca is not None:
            payload["busca"] = busca
        if orgao is not None:
            payload["orgao"] = orgao
        if ativo is not None:
            payload["ativo"] = ativo
        return self._post("listar_cursos", payload)

    def criar_curso(self, session_token: str, nome: str, conclusao: str, carga_horaria: float, ementa: str, orgao: str) -> dict[str, Any]:
        return self._post("criar_curso", {
            "session_token": session_token,
            "nome": nome,
            "conclusao": conclusao,
            "carga_horaria": carga_horaria,
            "ementa": ementa,
            "orgao": orgao,
        })

    def editar_curso(self, session_token: str, id_curso: str, nome: str, conclusao: str, carga_horaria: float, ementa: str, orgao: str) -> dict[str, Any]:
        return self._post("editar_curso", {
            "session_token": session_token,
            "id_curso": id_curso,
            "nome": nome,
            "conclusao": conclusao,
            "carga_horaria": carga_horaria,
            "ementa": ementa,
            "orgao": orgao,
        })

    def excluir_curso(self, session_token: str, id_curso: str) -> dict[str, Any]:
        return self._post("excluir_curso", {"session_token": session_token, "id_curso": id_curso})

    def listar_certificados(self, session_token: str, busca: str | None = None, curso: str | None = None, ativo: bool | None = True, data_inicio: str | None = None, data_fim: str | None = None) -> dict[str, Any]:
        payload = {"session_token": session_token}
        if busca is not None:
            payload["busca"] = busca
        if curso is not None:
            payload["curso"] = curso
        if ativo is not None:
            payload["ativo"] = ativo
        if data_inicio is not None:
            payload["data_inicio"] = data_inicio
        if data_fim is not None:
            payload["data_fim"] = data_fim
        return self._post("listar_certificados", payload)

    def criar_certificado(self, session_token: str, nome: str, cpf: str, curso: str) -> dict[str, Any]:
        return self._post("criar_certificado", {"session_token": session_token, "nome": nome, "cpf": cpf, "curso": curso})

    def editar_certificado(self, session_token: str, cod_validacao: str, nome: str, cpf: str, curso: str) -> dict[str, Any]:
        return self._post("editar_certificado", {
            "session_token": session_token,
            "cod_validacao": cod_validacao,
            "nome": nome,
            "cpf": cpf,
            "curso": curso,
        })

    def excluir_certificado(self, session_token: str, cod_validacao: str) -> dict[str, Any]:
        return self._post("excluir_certificado", {"session_token": session_token, "cod_validacao": cod_validacao})

    def criar_certificados_lote(self, session_token: str, curso: str, registros: list[dict[str, Any]]) -> dict[str, Any]:
        return self._post("criar_certificados_lote", {
            "session_token": session_token,
            "curso": curso,
            "registros": registros,
        })
