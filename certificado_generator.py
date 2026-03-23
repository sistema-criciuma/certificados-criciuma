from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from utils import format_carga_horaria_display, format_date_br, mask_cpf, normalize_cpf

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
LAYOUT_CONFIG_PATH = BASE_DIR / "layout_config.json"

DEFAULT_FONT = "Helvetica"


def load_layout_config() -> dict[str, Any]:
    if not LAYOUT_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado: {LAYOUT_CONFIG_PATH}"
        )
    return json.loads(LAYOUT_CONFIG_PATH.read_text(encoding="utf-8"))


def template_path_for_orgao(orgao_id: str, config: dict[str, Any] | None = None) -> Path:
    config = config or load_layout_config()
    templates_dir_name = config.get("templates_dir", "templates")
    templates_dir = BASE_DIR / templates_dir_name
    path = templates_dir / f"{orgao_id}.pdf"
    if not path.exists():
        raise FileNotFoundError(
            f"Template não encontrado para o órgão '{orgao_id}'. Esperado: {path}"
        )
    return path


def template_exists_for_orgao(orgao_id: str, config: dict[str, Any] | None = None) -> bool:
    try:
        return template_path_for_orgao(orgao_id, config).exists()
    except FileNotFoundError:
        return False


def get_layout_for_orgao(config: dict[str, Any], orgao_id: str) -> list[dict[str, Any]]:
    layouts = config.get("layouts", {})
    if orgao_id in layouts and layouts[orgao_id]:
        return layouts[orgao_id]
    return layouts.get("default", [])


def compose_dizeres(record: dict[str, Any]) -> str:
    cpf_mascarado = record.get("cpf_mascarado") or mask_cpf(record.get("cpf", ""))
    curso_nome = str(record.get("curso_nome", "") or "")
    conclusao_br = format_date_br(record.get("conclusao", ""))
    carga_horaria = format_carga_horaria_display(record.get("carga_horaria", ""))

    return (
        f"portador(a) do CPF {cpf_mascarado}, por concluir o curso "
        f"{curso_nome} em {conclusao_br}, com carga horária de {carga_horaria} hora(s)."
    )


def _prepare_context(record: dict[str, Any]) -> dict[str, str]:
    conclusao_br = format_date_br(record.get("conclusao", ""))
    carga_horaria = format_carga_horaria_display(record.get("carga_horaria", ""))
    cpf_limpo = normalize_cpf(record.get("cpf", ""))
    cpf_mascarado = record.get("cpf_mascarado") or mask_cpf(cpf_limpo)

    context = {
        "nome": str(record.get("nome", "") or ""),
        "cpf": cpf_limpo,
        "cpf_mascarado": str(cpf_mascarado or ""),
        "curso_nome": str(record.get("curso_nome", "") or ""),
        "orgao_nome": str(record.get("orgao_nome", "") or ""),
        "orgao": str(record.get("orgao", "") or ""),
        "ementa": str(record.get("ementa", "") or ""),
        "conclusao": str(record.get("conclusao", "") or ""),
        "conclusao_texto": conclusao_br,
        "carga_horaria": str(carga_horaria),
        "carga_horaria_texto": f"{carga_horaria} hora(s)",
        "cod_validacao": str(record.get("cod_validacao", "") or ""),
        "cod_validacao_texto": f"Código de validação: {record.get('cod_validacao', '')} - pode ser validado no site certificados-criciuma.streamlit.app",
    }

    context["dizeres"] = compose_dizeres(
        {
            **record,
            "cpf_mascarado": cpf_mascarado,
            "conclusao": record.get("conclusao", ""),
            "carga_horaria": record.get("carga_horaria", ""),
        }
    )

    return context


def _string_width(text: str, font_name: str, font_size: float) -> float:
    return pdfmetrics.stringWidth(text, font_name, font_size)


def _wrap_text_by_width(
    text: str,
    max_width: float,
    font_name: str,
    font_size: float,
) -> list[str]:
    text = str(text or "").strip()
    if not text:
        return [""]

    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]

    for word in words[1:]:
        test = f"{current} {word}"
        if _string_width(test, font_name, font_size) <= max_width:
            current = test
        else:
            lines.append(current)
            current = word

    lines.append(current)
    return lines


def _draw_text_block(
    canv: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    font_name: str,
    font_size: float,
    align: str,
    max_width: float,
    line_spacing: float,
) -> None:
    canv.setFont(font_name, font_size)

    lines = _wrap_text_by_width(
        text=text,
        max_width=max_width,
        font_name=font_name,
        font_size=font_size,
    )

    line_height = font_size * line_spacing

    for idx, line in enumerate(lines):
        yy = y - (idx * line_height)

        if align == "center":
            xx = x + (max_width / 2)
            canv.drawCentredString(xx, yy, line)
        elif align == "right":
            xx = x + max_width
            canv.drawRightString(xx, yy, line)
        else:
            canv.drawString(x, yy, line)


def _make_overlay(
    record: dict[str, Any],
    template_reader: PdfReader,
    placements: list[dict[str, Any]],
) -> PdfReader:
    packet = io.BytesIO()

    first_page = template_reader.pages[0]
    page_width = float(first_page.mediabox.width)
    page_height = float(first_page.mediabox.height)

    canv = canvas.Canvas(packet, pagesize=(page_width, page_height))
    context = _prepare_context(record)

    total_pages = len(template_reader.pages)

    for page_index in range(total_pages):
        current_page = template_reader.pages[page_index]
        current_width = float(current_page.mediabox.width)
        current_height = float(current_page.mediabox.height)

        # Atualiza o tamanho da página corrente no overlay
        canv.setPageSize((current_width, current_height))

        page_fields = [
            field for field in placements
            if field.get("enabled", True) and int(field.get("page", 0)) == page_index
        ]

        for field in page_fields:
            text_key = field.get("text_key", "")
            text = context.get(text_key, "")

            x = float(field.get("x", 0))
            y = float(field.get("y", 0))
            font_size = float(field.get("font_size", 12))
            align = str(field.get("align", "left") or "left").lower()
            max_width = float(field.get("max_width", 300))
            line_spacing = float(field.get("line_spacing", 1.2))

            _draw_text_block(
                canv=canv,
                text=text,
                x=x,
                y=y,
                font_name=DEFAULT_FONT,
                font_size=font_size,
                align=align,
                max_width=max_width,
                line_spacing=line_spacing,
            )

        canv.showPage()

    canv.save()
    packet.seek(0)
    return PdfReader(packet)


def build_certificado_pdf(record: dict[str, Any]) -> bytes:
    config = load_layout_config()

    orgao_id = str(record.get("orgao", "") or "")
    template_path = template_path_for_orgao(orgao_id, config)
    placements = get_layout_for_orgao(config, orgao_id)

    if not placements:
        raise ValueError(
            f"Nenhum layout encontrado em layout_config.json para o órgão '{orgao_id}' "
            f"nem em 'default'."
        )

    template_reader = PdfReader(str(template_path))
    overlay_reader = _make_overlay(
        record=record,
        template_reader=template_reader,
        placements=placements,
    )

    writer = PdfWriter()

    for idx, template_page in enumerate(template_reader.pages):
        if idx >= len(overlay_reader.pages):
            raise ValueError(
                f"Overlay gerado com menos páginas do que o template. "
                f"Template: {len(template_reader.pages)}, overlay: {len(overlay_reader.pages)}"
            )

        template_page.merge_page(overlay_reader.pages[idx])
        writer.add_page(template_page)

    output = io.BytesIO()
    writer.write(output)
    output.seek(0)
    return output.getvalue()


def build_certificados_zip(records: list[dict[str, Any]]) -> bytes:
    output = io.BytesIO()

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for record in records:
            pdf_bytes = build_certificado_pdf(record)
            filename = f'{record.get("cod_validacao", "certificado")}.pdf'
            zf.writestr(filename, pdf_bytes)

    output.seek(0)
    return output.getvalue()


def save_certificado_pdf(record: dict[str, Any], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    pdf_bytes = build_certificado_pdf(record)
    output_path.write_bytes(pdf_bytes)
    return output_path


if __name__ == "__main__":
    exemplo = {
        "nome": "Maria das Dores da Silva dos Santos",
        "cpf": "12345678911",
        "cpf_mascarado": "123.***.***-11",
        "curso_nome": "Nome do curso",
        "orgao_nome": "Secretaria Municipal de Educação",
        "orgao": "sme",
        "ementa": (
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
            "Praesent eget tortor non turpis lacinia tristique."
        ),
        "conclusao": "2025-09-15",
        "carga_horaria": 20,
        "cod_validacao": "ABC123XYZ7890001",
    }

    destino = BASE_DIR / "teste_certificado.pdf"
    save_certificado_pdf(exemplo, destino)
    print(f"PDF de teste gerado em: {destino}")