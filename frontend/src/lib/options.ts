/**
 * Opções das tabelas de códigos. Os valores espelham o backend (leiaute SPREV,
 * Deliberação TCE-RJ 260) — mantenha os dois lados iguais.
 */
type Opt = { value: string | number; label: string };
const o = (pairs: [string | number, string][]): Opt[] => pairs.map(([value, label]) => ({ value, label }));

export const UF_OPTIONS = o(
  "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split(" ").map((u) => [u, u]),
);

export const INSTITUTION_KIND = o([
  ["RPPS", "RPPS (instituto ou fundo de previdência)"], ["PREFEITURA", "Prefeitura"],
  ["AUTARQUIA", "Autarquia"], ["FUNDACAO", "Fundação pública"], ["CAMARA", "Câmara Municipal"], ["FUNDO", "Fundo municipal"],
]);

export const ENTE_KIND = o([["MUNICIPIO", "Município"], ["ESTADO", "Estado"], ["DF", "Distrito Federal"], ["UNIAO", "União"]]);

export const PODER = o([
  [1, "Executivo"], [2, "Legislativo"], [3, "Judiciário"], [4, "Ministério Público"], [5, "Tribunal de Contas"],
  [6, "Defensoria Pública"],
]);

export const TIPO_PODER = o([[1, "Administração Direta"], [2, "Administração Indireta"]]);

export const TIPO_CARGO = o([
  [1, "Magistrados, membros do MP ou de Tribunal de Contas"], [2, "Professor da educação infantil e ensino fundamental/médio"],
  [3, "Professor do ensino superior"], [4, "Policial civil"], [5, "Agente penitenciário"], [6, "Guarda municipal"],
  [7, "Demais servidores"], [8, "Militar"],
]);

export const SEX = o([[1, "Feminino"], [2, "Masculino"]]);

export const MARITAL = o([
  [1, "Solteiro(a)"], [2, "Casado(a)"], [3, "Viúvo(a)"], [4, "Separado(a) judicialmente"], [5, "Divorciado(a)"],
  [6, "União estável"], [9, "Outros"],
]);

export const DEPENDENCY = o([
  [1, "Cônjuge"], [2, "Companheiro(a)"], [3, "Filho(a) menor não emancipado(a)"], [4, "Filho(a) inválido(a)"],
  [5, "Pai/mãe com dependência econômica"], [6, "Enteado(a) menor, com dependência econômica"],
  [7, "Enteado(a) inválido(a), com dependência econômica"], [8, "Irmão(ã) menor, com dependência econômica"],
  [9, "Irmão(ã) inválido(a), com dependência econômica"], [10, "Menor tutelado"], [11, "Neto(a)"],
  [12, "Ex-cônjuge que recebe pensão de alimentos"], [99, "Outros"],
]);

export const ACCOUNT_TYPE = o([["CORRENTE", "Conta corrente"], ["POUPANCA", "Conta poupança"], ["SALARIO", "Conta salário"]]);

export const DOC_TYPE = o([
  ["IDENTIDADE", "Identidade (RG/CNH)"], ["CPF", "CPF"], ["CERT_NASC", "Certidão de nascimento"],
  ["CERT_CASAMENTO", "Certidão de casamento / união estável"], ["CERT_OBITO", "Certidão de óbito"],
  ["RESIDENCIA", "Comprovante de residência"], ["TITULO", "Título de eleitor"], ["RESERVISTA", "Certificado de reservista"],
  ["PIS", "PIS/PASEP"], ["ESCOLARIDADE", "Comprovante de escolaridade"], ["LAUDO", "Laudo médico"],
  ["NOMEACAO", "Ato de nomeação"], ["POSSE", "Termo de posse / exercício"], ["EXAME_ADM", "Exame admissional"],
  ["DECL_BENS", "Declaração de bens"], ["DECL_ACUMUL", "Declaração de acumulação de cargos"],
  ["FICHA_FUNC", "Ficha funcional"], ["CONTRACHEQUE", "Contracheque"], ["CTC", "Certidão de Tempo de Contribuição"],
  ["ATO", "Ato / portaria / decreto"], ["OUTROS", "Outros"],
]);

/** Pasta de cada tipo de documento (espelha people.models.doc_folder). */
export const DOC_FOLDERS: { key: string; label: string; types: string[] }[] = [
  { key: "PESSOAIS", label: "Documentos pessoais",
    types: ["IDENTIDADE", "CPF", "CERT_NASC", "CERT_CASAMENTO", "CERT_OBITO", "RESIDENCIA", "TITULO", "RESERVISTA", "PIS", "ESCOLARIDADE", "LAUDO"] },
  { key: "FUNCIONAIS", label: "Documentos funcionais",
    types: ["NOMEACAO", "POSSE", "EXAME_ADM", "DECL_BENS", "DECL_ACUMUL", "FICHA_FUNC", "CONTRACHEQUE", "CTC", "ATO"] },
  { key: "OUTROS", label: "Outros", types: ["OUTROS"] },
];

export const LINK_TYPE = o([
  [1, "Servidor efetivo"], [2, "Efetivo ocupante de cargo em comissão"], [3, "Estável (art. 19 ADCT)"], [4, "Outros"],
]);

export const REGIME = o([["ESTATUTARIO", "Estatutário (RPPS)"], ["CELETISTA", "Celetista (RGPS)"]]);

export const ADMISSION_FORM = o([
  [1, "Contrato temporário"], [2, "Contrato por prazo indeterminado"], [3, "Concurso público"], [4, "Nomeação direta"],
]);

export const ELIGIBILITY = o([
  [1, "Sem critério diferenciado"], [2, "Com deficiência (art. 40, § 4º, I)"], [3, "Professor"],
  [4, "Atividade de risco (art. 40, § 4º, II)"], [5, "Atividade prejudicial à saúde (art. 40, § 4º, III)"],
]);

export const SITUATION = o([
  [1, "Em exercício"], [2, "Licenciado(a) com remuneração"], [3, "Licenciado(a) sem remuneração"],
  [4, "Cedido(a) com ônus"], [5, "Cedido(a) sem ônus"], [6, "Requisitado(a) com ônus"], [7, "Requisitado(a) sem ônus"],
  [8, "Em disponibilidade"], [9, "Afastado(a) para mandato eletivo"], [10, "Recluso(a) ou detido(a)"], [11, "Outros"],
]);

export const SEGMENT = o([
  ["FINANCEIRO", "Plano Financeiro"], ["PREVIDENCIARIO", "Plano Previdenciário — massa própria"],
  ["COMPRA_VIDAS", "Plano Previdenciário — Compra de Vidas"],
]);

export const LINK_CLOSE_STATUS = o([
  ["APOSENTADO", "Aposentado"], ["EXONERADO", "Exonerado / demitido"], ["FALECIDO", "Falecido"],
  ["ENCERRADO", "Encerrado (outros motivos)"],
]);

export const EVENT_TYPE = o([
  ["NOMEACAO", "Nomeação / admissão"], ["POSSE", "Posse / exercício"], ["PROGRESSAO", "Progressão / promoção"],
  ["ENQUADRAMENTO", "Enquadramento / transformação de cargo"], ["LOTACAO", "Mudança de lotação"], ["LICENCA", "Licença"],
  ["AFASTAMENTO", "Afastamento"], ["FALTAS", "Faltas não abonadas"], ["SUSPENSAO", "Suspensão"],
  ["DISPONIBILIDADE", "Disponibilidade"], ["CESSAO", "Cessão / requisição"], ["RETORNO", "Retorno ao exercício"],
  ["ABONO", "Concessão de abono de permanência"], ["GRATIFICACAO", "Gratificação / vantagem"], ["OUTROS", "Outros"],
]);

export const PRIORITY = o([
  ["NORMAL", "Normal"], ["IDOSO", "Pessoa idosa (60+)"], ["DEFICIENCIA", "Pessoa com deficiência"],
  ["DOENCA_GRAVE", "Doença grave"], ["JUDICIAL", "Determinação judicial"],
]);

/** Natureza do tempo de serviço (Deliberação TCE-RJ 260). */
export const TIME_NATURE = o([
  ["01", "INSS — iniciativa privada"], ["02", "INSS — órgão público"], ["03", "RPPS de outro órgão público"],
  ["04", "Forças Armadas"], ["05", "RPPS do órgão de origem"],
]);

export const HOLIDAY_KIND = o([
  ["NACIONAL", "Nacional"], ["ESTADUAL", "Estadual"], ["MUNICIPAL", "Municipal"], ["PONTO_FACULTATIVO", "Ponto facultativo"],
]);
