"""
Consulta de CPF na Receita Federal via Conecta gov.br — API "CPF Light"
(Cadastro Base do Cidadão), gratuita para órgãos públicos aderentes.

Configuração (backend/.env), fornecida pelo Conecta após a adesão:
    CONECTA_CLIENT_ID, CONECTA_CLIENT_SECRET
    CONECTA_AMBIENTE = homologacao | producao   (padrão: homologacao)

Sem credenciais a consulta fica indisponível e o sistema informa isso — nunca
simula resposta. Cada consulta é registrada na auditoria (LGPD) e envia, como
exige a API, o CPF do usuário que consultou (cabeçalho x-cpf-usuario).

Atenção: na Receita, Sexo 1 = masculino e 2 = feminino; no leiaute SPREV
(usado no cadastro) é o contrário — a conversão é feita aqui.
"""
import base64
import json
import urllib.error
import urllib.request
from datetime import datetime

from django.conf import settings
from django.core.cache import cache

from apps.core.exceptions import BusinessRuleError
from apps.core.validators import only_digits

HOSTS = {
    "producao": "https://apigateway.conectagov.estaleiro.serpro.gov.br",
    "homologacao": "https://h-apigateway.conectagov.np.estaleiro.serpro.gov.br",
}
TOKEN_CACHE_KEY = "conecta_cpf_token"
TIMEOUT = 15
MAX_BATCH = 50
SEX_FROM_RECEITA = {1: 2, 2: 1}  # Receita (1=M, 2=F) -> SPREV (1=F, 2=M)


def _config():
    cid = getattr(settings, "CONECTA_CLIENT_ID", "") or ""
    secret = getattr(settings, "CONECTA_CLIENT_SECRET", "") or ""
    env = (getattr(settings, "CONECTA_AMBIENTE", "") or "homologacao").lower()
    return cid, secret, HOSTS.get(env, HOSTS["homologacao"]), env


def is_configured() -> bool:
    cid, secret, _, _ = _config()
    return bool(cid and secret)


def _request(url, data: bytes, headers: dict) -> bytes:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            cache.delete(TOKEN_CACHE_KEY)
            raise BusinessRuleError("O Conecta gov.br recusou as credenciais. Verifique a adesão e a chave de acesso.")
        raise BusinessRuleError(f"A Receita Federal (Conecta gov.br) respondeu com erro {exc.code}.")
    except (urllib.error.URLError, TimeoutError):
        raise BusinessRuleError("Não foi possível conectar ao Conecta gov.br. Tente novamente em instantes.")


def _token() -> str:
    token = cache.get(TOKEN_CACHE_KEY)
    if token:
        return token
    cid, secret, host, _ = _config()
    basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    raw = _request(f"{host}/oauth2/jwt-token", b"grant_type=client_credentials", {
        "Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded",
    })
    payload = json.loads(raw)
    token = payload["access_token"]
    # Token vale cerca de 2 horas; renova antes
    cache.set(TOKEN_CACHE_KEY, token, timeout=max(int(payload.get("expires_in", 7200)) - 300, 60))
    return token


def _date(v):
    s = only_digits(str(v or ""))
    try:
        return datetime.strptime(s, "%Y%m%d").date().isoformat() if len(s) == 8 else None
    except ValueError:
        return None


def normalize(item: dict) -> dict:
    """Converte a resposta da Receita para os campos do cadastro."""
    street = " ".join(p for p in (item.get("TipoLogradouro"), item.get("Logradouro")) if p).strip()
    cep = only_digits(str(item.get("Cep") or ""))
    return {
        "cpf": only_digits(item.get("Cpf")),
        "name": (item.get("Nome") or "").strip(),
        "social_name": (item.get("NomeSocial") or "").strip(),
        "birth_date": _date(item.get("DataNascimento")),
        "sex": SEX_FROM_RECEITA.get(item.get("Sexo")),
        "mother_name": (item.get("NomeMae") or "").strip(),
        "birthplace_city": (item.get("NomeMunicipioNacionalidade") or item.get("NomeMunicipioNaturalidade") or "").strip(),
        "birthplace_uf": (item.get("UFMunicipioNaturalidade") or "").strip()[:2],
        "nationality": "Estrangeira" if item.get("Estrangeiro") == "S" else "Brasileira",
        "situacao_cadastral": (item.get("DescSituacaoCadastral") or "").strip(),
        "ano_obito": item.get("AnoObito") or None,
        "endereco": {
            "street": street, "number": str(item.get("NumeroLogradouro") or "").strip(),
            "complement": (item.get("Complemento") or "").strip(), "district": (item.get("Bairro") or "").strip(),
            "city": (item.get("Municipio") or "").strip(), "uf": (item.get("UF") or "").strip()[:2],
            "cep": cep.zfill(8) if cep else "",
        },
    }


def consult(cpfs: list[str], requester_cpf: str) -> dict[str, dict]:
    """Consulta até 50 CPFs. Retorna {cpf: dados normalizados}."""
    if not is_configured():
        raise BusinessRuleError(
            "Consulta à Receita Federal não configurada. Após a adesão ao Conecta gov.br, informe "
            "CONECTA_CLIENT_ID e CONECTA_CLIENT_SECRET no arquivo de configuração do servidor."
        )
    requester = only_digits(requester_cpf)
    if len(requester) != 11:
        raise BusinessRuleError("Cadastre o seu CPF no seu perfil de usuário: a Receita exige o CPF de quem consulta.")
    cpfs = [only_digits(c) for c in cpfs if only_digits(c)][:MAX_BATCH]
    if not cpfs:
        return {}
    _, _, host, _ = _config()
    raw = _request(f"{host}/api-cpf-light/v2/consulta/cpf", json.dumps({"listaCpf": cpfs}).encode(), {
        "Authorization": f"Bearer {_token()}", "Content-Type": "application/json", "x-cpf-usuario": requester,
    })
    data = json.loads(raw) or []
    return {n["cpf"]: n for n in (normalize(i) for i in data) if n["cpf"]}
