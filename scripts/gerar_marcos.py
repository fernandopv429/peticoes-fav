#!/usr/bin/env python3
"""Gera a peça do caso MARCOS a partir da ENTREVISTA ASSINADA.

Caso de referência do projeto: existe peça real feita por especialista
("Analise IA/MARCOS/Feita pela especialista.docx", R$ 70.268,67), então é
contra ela que se mede qualquer mudança no motor.

A fonte aqui é a ENTREVISTA ASSINADA em PDF, não o registro do app Base44 —
o registro `6a7a00a5045fd0690aaaf3dc` contradiz o formulário assinado
(06:00-18:00 contra 19h-7h, 1-2 FTs contra 5-6) e produziria outra peça.

    python scripts/gerar_marcos.py            # sem IA: só a estrutura
    python scripts/gerar_marcos.py --ia       # com redação (custa 1 chamada Opus)
    python scripts/gerar_marcos.py --ia --pdf # e converte pelo n8n
"""
import sys
import pathlib
from datetime import date
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.modelos import Caso, Reclamada          # noqa: E402
from app.pipeline import gerar                   # noqa: E402

SAIDA = pathlib.Path(__file__).resolve().parent.parent / "data" / "saida"


def caso_marcos() -> Caso:
    return Caso(
        nome="Marcos Moreira Paulo",
        funcao="Vigilante",
        nacionalidade="brasileiro",
        estado_civil="solteiro",
        rg="672853966 São Paulo/SP",
        cpf="105.678.257-95",
        pis="1290165260-5",
        ctps="105678",
        ctps_serie="25795",
        nascimento=date(1983, 7, 8),
        filiacao="Jose Paulo Irmao e Damiana Moreira Paulo",
        endereco="Rua Antonio de Albuquerque nº 181, cs 03, Aldeinha, "
                 "Itapecerica da Serra/SP",
        cep="CEP 06877-150",
        email="marcos81769111@gmail.com",

        admissao=date(2025, 4, 14),
        rescisao=date(2025, 12, 7),
        modalidade="sem_justa_causa",
        # a entrevista não coleta salário; é o piso da categoria na CCT vigente
        salario=Decimal("2148.22"),

        reclamadas=[
            Reclamada(razao_social="VIGSEG VIGILANCIA E SEGURANCA DE VALORES LTDA",
                      cnpj="04.542.518/0002-99",
                      endereco="Prq Domingos Luis, 699 - Jardim São Paulo "
                               "(Zona Norte) - São Paulo/SP"),
            Reclamada(razao_social="GLP RÉGIS (Integral Médica)",
                      cnpj="46.652.606/0001-02",
                      endereco="Rod. Régis Bittencourt, sn - km 296,5 - "
                               "Itaquaciara - Itapecerica da Serra/SP, CEP 06877-115",
                      tomadora=True),
        ],
        municipio_prestacao="Itapecerica da Serra", uf_prestacao="SP",
        endereco_prestacao="Rod. Régis Bittencourt, sn - km 296,5 - Itaquaciara - "
                           "Itapecerica da Serra/SP, CEP 06877-115",

        escala="12x36",
        jornada_horario="das 19h às 7h",
        media_horas_extras="1h",
        periodo_antecedente="30 min",
        periodo_sucedente="30 min",
        trabalhou_fins_de_semana=True,
        tem_adicional_noturno=True,           # 19h-7h cobre as 22h-5h
        intervalo_suprimido=True,
        intervalo_gozado="Rádio HT sempre ligado",

        vale_refeicao=True, vale_alimentacao=True, vale_transporte=True,
        # valor_alimentacao_dia vem da CCT (cláusula do ticket-refeição);
        # valor_transporte_dia a entrevista NÃO coleta — sem ele o pedido de
        # VT nas folgas não sai com número.

        tem_periculosidade=True,
        tem_dano_moral=True,          # tese padrão da banca; a IA ancora no fato
        tem_espelho_ponto=False, tem_holerites=True,
        desconto_indevido="desconto integral do saldo devedor do empréstimo "
                          "consignado na rescisão",

        # "Acúmulo/Desvio: Sim" — vigilante que passou a acumular Prevenção de
        # Perdas. Ver a nota em entrevista.py sobre desvio x acúmulo.
        tem_desvio=True,
        funcoes_acumuladas="conferência de mercadorias, controle e verificação de "
                           "validade de produtos, registros operacionais, conferência "
                           "de cargas, controle da quantidade de paletes e demais "
                           "procedimentos do setor de Prevenção de Perdas",

        folgas_trabalhadas_mes=Decimal("5.5"),   # "5 a 6" -> média
        val_folgas_mensal=Decimal("180"),        # "180 a 200" -> extremo conservador
        ft_forma_pagamento="pix, fora da folha",

        fatos_narrados=(
            "Após o desligamento do colaborador responsável pela Prevenção de "
            "Perdas, passou a acumular as atribuições da função sem qualquer "
            "contraprestação adicional. Realizava em média 5 a 6 folgas "
            "trabalhadas por mês, pagas por fora da folha. Teve o saldo devedor "
            "do empréstimo consignado descontado integralmente na rescisão."),
    )


def main() -> None:
    com_ia = "--ia" in sys.argv
    com_pdf = "--pdf" in sys.argv

    r = gerar(caso_marcos(), codigo="MARCOS", municipio="Itapecerica da Serra",
              redigir_ia=com_ia)

    print("\n".join(f"  {t}" for t in r.trace))
    print(f"\nvalor da causa: R$ {r.valor_causa:,.2f}".replace(",", "@")
          .replace(".", ",").replace("@", "."))
    print(f"gate: {'APROVADO' if r.validacao.aprovado else 'REPROVADO'}")
    for p in r.validacao.problemas:
        print(f"  ! {p}")

    SAIDA.mkdir(parents=True, exist_ok=True)
    destino = SAIDA / "marcos.html"
    destino.write_text(r.html, encoding="utf-8")
    print(f"\nHTML: {destino}")

    if com_pdf:
        from app.pdf import gerar_pdf
        pdf = SAIDA / "marcos.pdf"
        pdf.write_bytes(gerar_pdf(r.html, nome="marcos.pdf"))
        print(f"PDF:  {pdf}")


if __name__ == "__main__":
    main()
