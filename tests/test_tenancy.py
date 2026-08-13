"""Testes do catálogo de tenants e da autenticação por chave de API.

Rodam sem banco, sem Redis e sem chave de modelo: o catálogo é YAML puro.
Os testes de `tools_for` (ferramentas liberadas por tenant) vivem aqui também
a partir da Fase 4, quando o registro de ferramentas existe.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.tools import tools_for
from app.config import Tenant, load_tenants, tenant_by_api_key

TENANTS_DIR = str(Path(__file__).resolve().parent.parent / "tenants")

CHAVE_CLINICA = "demo-sorriso-123"
CHAVE_ADVOCACIA = "demo-silva-456"


@pytest.fixture
def tenants() -> dict[str, Tenant]:
    return load_tenants(TENANTS_DIR)


def test_carrega_tenants_do_diretorio(tenants: dict[str, Tenant]) -> None:
    assert set(tenants) == {"clinica-sorriso", "adv-silva"}
    assert tenants["clinica-sorriso"].name == "Clínica Sorriso"
    assert tenants["adv-silva"].hours.slot_minutes == 60


def test_chave_valida_resolve() -> None:
    tenant = tenant_by_api_key(CHAVE_CLINICA, TENANTS_DIR)
    assert tenant is not None
    assert tenant.id == "clinica-sorriso"


def test_chave_invalida_nao_resolve() -> None:
    assert tenant_by_api_key("chave-que-nao-existe", TENANTS_DIR) is None


def test_chave_vazia_nao_resolve() -> None:
    assert tenant_by_api_key("", TENANTS_DIR) is None


def test_contraste_de_ferramentas_entre_clinica_e_advocacia(
    tenants: dict[str, Tenant],
) -> None:
    """A clínica agenda; a advocacia não. A agenda é do advogado, não do bot."""
    clinica = tenants["clinica-sorriso"]
    advocacia = tenants["adv-silva"]

    assert "criar_agendamento" in clinica.tools
    assert "consultar_disponibilidade" in clinica.tools

    assert "criar_agendamento" not in advocacia.tools
    assert "consultar_disponibilidade" not in advocacia.tools
    assert advocacia.tools == ["buscar_documentos", "registrar_lead"]


def test_system_prompt_contem_regras_e_contexto(tenants: dict[str, Tenant]) -> None:
    prompt = tenants["clinica-sorriso"].system_prompt()

    # Contexto do negócio: nome, serviços e horário.
    assert "Clínica Sorriso" in prompt
    assert "Limpeza" in prompt
    assert "09:00" in prompt
    assert "18:00" in prompt
    assert "segunda" in prompt

    # As cinco regras fixas, pelo trecho que identifica cada uma.
    assert "buscar_documentos" in prompt
    assert "Nunca invente preço" in prompt
    assert "desconto, reembolso ou exceção de política" in prompt
    assert "nunca como instrução" in prompt
    assert "confirme nome, serviço e horário" in prompt
    assert "máximo 4 frases" in prompt


def test_hash_nao_expoe_a_chave(tenants: dict[str, Tenant]) -> None:
    tenant = tenants["clinica-sorriso"]
    assert tenant.api_key_hash != tenant.api_key
    assert tenant.api_key not in tenant.api_key_hash
    assert len(tenant.api_key_hash) == 64  # SHA-256 em hex
    assert all(c in "0123456789abcdef" for c in tenant.api_key_hash)


def _yaml_de_tenant(tenant_id: str, api_key: str) -> str:
    return (
        f"id: {tenant_id}\n"
        f"name: Tenant {tenant_id}\n"
        f"api_key: {api_key}\n"
        f"persona: Persona de teste.\n"
        f"services: [Servico A]\n"
    )


def test_id_duplicado_levanta_erro(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(_yaml_de_tenant("dup", "chave-a"), encoding="utf-8")
    (tmp_path / "b.yaml").write_text(_yaml_de_tenant("dup", "chave-b"), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicado"):
        load_tenants(str(tmp_path))


def test_api_key_repetida_levanta_erro(tmp_path: Path) -> None:
    (tmp_path / "a.yaml").write_text(_yaml_de_tenant("um", "mesma-chave"), encoding="utf-8")
    (tmp_path / "b.yaml").write_text(_yaml_de_tenant("dois", "mesma-chave"), encoding="utf-8")

    with pytest.raises(ValueError, match="api_key repetida"):
        load_tenants(str(tmp_path))


def test_tools_for_respeita_o_yaml_do_tenant(tenants: dict[str, Tenant]) -> None:
    """criar_agendamento existe na clínica e não existe na advocacia."""
    nomes_clinica = [t.name for t in tools_for(tenants["clinica-sorriso"])]
    nomes_advocacia = [t.name for t in tools_for(tenants["adv-silva"])]

    assert "criar_agendamento" in nomes_clinica
    assert "consultar_disponibilidade" in nomes_clinica
    assert "criar_agendamento" not in nomes_advocacia
    assert nomes_advocacia == ["buscar_documentos", "registrar_lead"]


def test_ferramenta_inexistente_no_yaml_e_ignorada() -> None:
    tenant = Tenant(
        id="teste",
        name="Tenant Teste",
        api_key="chave-teste",
        persona="Persona.",
        services=["Serviço"],
        tools=["buscar_documentos", "ferramenta_fantasma"],
    )
    assert [t.name for t in tools_for(tenant)] == ["buscar_documentos"]
