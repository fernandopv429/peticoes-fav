"""Schema do caso — a matriz fática que sai da entrevista.

Só dados. Nada aqui é decidido por IA: ou vem do formulário, ou vem de consulta
(CNPJ/CEP/CCT), ou é calculado.
"""
from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field

Categoria = Literal["vigilancia", "asseio_conservacao", "terceirizados"]
# Base de contagem das verbas por hora. As peças reais divergem: a do MARCOS
# conta por PLANTÃO (15/mês numa 12x36), a do JONATHAN conta por DIA DO MÊS
# (~30) para a mesma rubrica — o dobro. Não há constante que reproduza as duas,
# então vira decisão, com o conservador como padrão.
CriterioHoras = Literal["por_plantao", "por_dia_do_mes"]
Sindicato = Literal["SEEVISSP", "SIEMACO", "SINDEEPRES"]
Modalidade = Literal["sem_justa_causa", "rescisao_indireta", "coacao_demissao",
                     "reversao_justa_causa", "acordo"]


class Reclamada(BaseModel):
    razao_social: str
    cnpj: Optional[str] = None
    endereco: Optional[str] = None
    tomadora: bool = False
    # CNAE principal (BrasilAPI: `cnae_fiscal`). É o que distingue SIEMACO de
    # SINDEEPRES — a função do empregado não distingue: nos dois é
    # Controlador/Porteiro (MATRIZ_GERAL_3_MODELOS.md §2).
    cnae: Optional[str] = None


class Caso(BaseModel):
    # --- identificação
    nome: str
    genero: Literal["M", "F"] = "M"
    funcao: str
    reclamadas: list[Reclamada] = Field(default_factory=list)

    # --- contrato
    admissao: date
    rescisao: date
    modalidade: Modalidade
    salario: Decimal
    maior_remuneracao: Optional[Decimal] = None  # base do dano moral; default = salário
    categoria: Optional[Categoria] = None
    # Sindicato do holerite/TRCT. Prevalece sobre qualquer derivação automática —
    # é o que a empresa efetivamente aplicou.
    sindicato: Optional[Sindicato] = None

    # --- local da prestação (art. 651 CLT: define a competência, e NÃO o
    # domicílio do reclamante nem a sede da reclamada)
    municipio_prestacao: Optional[str] = None
    uf_prestacao: Optional[str] = None
    endereco_prestacao: Optional[str] = None

    # --- qualificação (vai direto para as tags do template)
    nacionalidade: Optional[str] = None
    estado_civil: Optional[str] = None
    rg: Optional[str] = None
    cpf: Optional[str] = None
    pis: Optional[str] = None
    ctps: Optional[str] = None
    ctps_serie: Optional[str] = None
    nascimento: Optional[date] = None
    filiacao: Optional[str] = None
    endereco: Optional[str] = None
    cep: Optional[str] = None
    # E-mail DA PARTE. O art. 319, II, do CPC pede o endereço eletrônico do autor;
    # o do escritório, que já consta do preâmbulo, é do advogado — não substitui.
    email: Optional[str] = None

    # --- jornada. Estes campos são o que a IA usa para ESTIMAR as verbas por
    # hora. Sem eles ela cai na heurística genérica: no caso MARCOS isso produziu
    # R$ 11.494 de horas extras onde a especialista estimou R$ 703, porque a
    # entrevista dizia "até 1 hora" e o dado não chegava até lá.
    escala: Optional[str] = None                 # "12x36", "5x2", "4x2", "6x1"
    criterio_horas: CriterioHoras = "por_plantao"
    jornada_horario: Optional[str] = None        # "das 19h às 07h"
    media_horas_extras: Optional[str] = None     # "Até 1 hora"
    periodo_antecedente: Optional[str] = None    # "30 minutos"
    periodo_sucedente: Optional[str] = None      # "30 minutos"
    trabalhou_fins_de_semana: bool = False
    tem_adicional_noturno: bool = False
    intervalo_suprimido: bool = False
    intervalo_gozado: Optional[str] = None       # "Rádio HT sempre ligado"

    # --- benefícios (cada um vira pedido próprio nas folgas trabalhadas)
    vale_refeicao: bool = False
    vale_alimentacao: bool = False
    vale_transporte: bool = False
    # Valores diários — vêm da CCT. Sem eles a rubrica não entra: não se arbitra
    # valor de benefício.
    valor_alimentacao_dia: Optional[Decimal] = None
    valor_transporte_dia: Optional[Decimal] = None
    # Cláusula de penas cominatórias da CCT, citada no pedido de multas
    # convencionais ("multa da cláusula 71ª"). Preenchida por `cct.enriquecer`.
    clausula_multa: Optional[str] = None

    # --- saúde e segurança
    tem_periculosidade: bool = False
    tem_insalubridade: bool = False
    tem_doenca_ocupacional: bool = False

    # --- documentos e descontos
    tem_espelho_ponto: bool = True               # ausência inverte o ônus da prova
    tem_holerites: bool = False
    desconto_indevido: Optional[str] = None

    # --- narrativa (fonte primária para a IA)
    fatos_narrados: Optional[str] = None
    funcoes_acumuladas: Optional[str] = None

    # --- teses
    tem_dano_moral: bool = False
    tem_desvio: bool = False
    meses_desvio: Optional[int] = None           # default = meses do contrato
    tem_acumulo: bool = False
    tem_gratificacao_funcao: bool = False        # vigilante condutor (10%)
    # Bonificação de assiduidade: verba distinta da gratificação de função — o
    # pedido é a DIFERENÇA entre o prometido e o efetivamente pago.
    tem_assiduidade: bool = False
    assiduidade_prometida: Optional[Decimal] = None
    assiduidade_paga: Optional[Decimal] = None
    folgas_trabalhadas_mes: Optional[Decimal] = None
    # ⚠️ Valor MENSAL pago por fora, não por folga. A peça da especialista diz
    # "gira em torno de R$ 180,00 mensais"; ler como por-folga inflou a rubrica
    # em 450% no caso MARCOS.
    val_folgas_mensal: Optional[Decimal] = None
    ft_forma_pagamento: Optional[str] = None
    salarios_em_aberto_meses: int = 0

    # --- percentuais da CCT (preenchidos por consulta; caem no default se ausente)
    pct_desvio: Decimal = Decimal("0.50")
    pct_acumulo: Decimal = Decimal("0.20")
    pct_gratificacao: Decimal = Decimal("0.10")

    @property
    def base_dano_moral(self) -> Decimal:
        return self.maior_remuneracao or self.salario

    @property
    def meses_contrato(self) -> int:
        """Meses cheios entre admissão e rescisão."""
        m = (self.rescisao.year - self.admissao.year) * 12 + \
            (self.rescisao.month - self.admissao.month)
        if self.rescisao.day < self.admissao.day:
            m -= 1
        return max(m, 0)

    def _meses_com_15_dias(self, inicio: date) -> int:
        """Meses entre `inicio` e a rescisão com ao menos 15 dias trabalhados
        (art. 146, § único, CLT)."""
        import calendar
        total, ano, mes = 0, inicio.year, inicio.month
        while (ano, mes) <= (self.rescisao.year, self.rescisao.month):
            ultimo = calendar.monthrange(ano, mes)[1]
            primeiro_dia = inicio.day if (ano, mes) == (inicio.year, inicio.month) else 1
            ultimo_dia = (self.rescisao.day
                          if (ano, mes) == (self.rescisao.year, self.rescisao.month)
                          else ultimo)
            if ultimo_dia - primeiro_dia + 1 >= 15:
                total += 1
            mes += 1
            if mes > 12:
                mes, ano = 1, ano + 1
        return min(total, 12)

    @property
    def avos_13(self) -> int:
        """13º: meses do ANO-CALENDÁRIO da rescisão (Lei 4.090/62)."""
        return self._meses_com_15_dias(max(self.admissao, date(self.rescisao.year, 1, 1)))

    @property
    def avos_ferias(self) -> int:
        """Férias: meses do PERÍODO AQUISITIVO, que corre da admissão (ou do seu
        aniversário), não do início do ano.

        As peças distinguem: no caso JONATHAN (admissão 25/01/2025, rescisão
        11/12/2025) a peça traz 13º = 12/12 e férias = **11/12** — 10 meses
        completos de 25/01 a 25/11, mais 16 dias até 11/12. Usar ano-calendário
        nos dois dava 10 e subestimava as férias."""
        inicio = self.admissao
        while date(inicio.year + 1, inicio.month, min(inicio.day, 28)) <= self.rescisao:
            inicio = date(inicio.year + 1, inicio.month, inicio.day)
        completos = 0
        marco = inicio
        while True:
            mes, ano = marco.month + 1, marco.year
            if mes > 12:
                mes, ano = 1, ano + 1
            import calendar
            proximo = date(ano, mes, min(marco.day, calendar.monthrange(ano, mes)[1]))
            if proximo > self.rescisao:
                break
            completos += 1
            marco = proximo
        resto = (self.rescisao - marco).days
        return min(completos + (1 if resto >= 15 else 0), 12)

    @property
    def avos(self) -> int:
        """Compatibilidade — usa o critério do 13º."""
        return self.avos_13
