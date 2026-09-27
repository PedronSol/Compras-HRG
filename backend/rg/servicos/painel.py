"""Indicadores do painel. Todas as consultas rodam sob RLS: o setor vê apenas o seu escopo,
Compras o que foi aprovado e Diretoria, Financeiro, Auditoria e Administrador tudo."""
from __future__ import annotations

from datetime import date

TERMINAIS = "('concluida', 'reprovada', 'cancelada')"
PEDIDO_VALIDO = "p.status not in ('reprovado', 'cancelado')"


def _f(v):
    return float(v) if v is not None else None


def painel(cur, inicio: date, fim: date, setor: str | None, tz: str) -> dict:
    p = {"ini": inicio, "fim": fim, "setor": setor, "tz": tz}
    filtro_s = ("(s.criado_em at time zone %(tz)s)::date between %(ini)s and %(fim)s"
                " and (%(setor)s::text is null or s.setor_codigo = %(setor)s)")
    filtro_p = ("(p.criado_em at time zone %(tz)s)::date between %(ini)s and %(fim)s"
                " and (%(setor)s::text is null or p.setor_codigo = %(setor)s)")
    setor_v = "(%(setor)s::text is null or v.setor_codigo = %(setor)s)"

    cur.execute(f"""
        select count(*) as solicitacoes,
               count(*) filter (where s.status = 'concluida') as concluidas,
               count(*) filter (where s.status in ('reprovada', 'cancelada')) as encerradas_sem_compra,
               avg(extract(epoch from (s.aprovado_em - s.criado_em)) / 86400.0) filter (where s.aprovado_em is not null)
                 as tempo_aprovacao_dias,
               avg(extract(epoch from (s.fornecedor_definido_em - s.cotacao_iniciada_em)) / 86400.0)
                 filter (where s.fornecedor_definido_em is not null) as tempo_cotacao_dias,
               avg(extract(epoch from (s.pedido_emitido_em - s.criado_em)) / 86400.0)
                 filter (where s.pedido_emitido_em is not null) as tempo_ate_pedido_dias,
               avg(extract(epoch from (s.finalizado_em - s.criado_em)) / 86400.0) filter (where s.status = 'concluida')
                 as lead_time_dias,
               avg(case when s.sla_concluido_em <= s.sla_prazo_limite then 1.0 else 0.0 end)
                 filter (where s.sla_concluido_em is not null and s.status not in ('reprovada', 'cancelada'))
                 as sla_cumprimento
          from rg.solicitacoes s where {filtro_s}""", p)
    kpis = cur.fetchone()

    cur.execute(f"""
        select count(*) filter (where v.status not in {TERMINAIS}) as abertas,
               count(*) filter (where v.status in ('aguardando_gestor', 'aguardando_diretoria', 'devolvida')) as em_aprovacao,
               count(*) filter (where v.status in ('aprovada', 'em_cotacao', 'aguardando_pedido')) as em_compras,
               count(*) filter (where v.status in ('em_pedido', 'recebida_parcial')) as aguardando_entrega,
               count(*) filter (where v.sla_situacao = 'estourado') as sla_estourado,
               count(*) filter (where v.sla_situacao = 'alerta') as sla_alerta,
               count(*) filter (where v.urgencia = 'imediato' and v.status not in {TERMINAIS}) as imediatas_abertas
          from rg.v_solicitacoes v where {setor_v}""", p)
    kpis.update(cur.fetchone())

    cur.execute(f"""
        select count(*) as pedidos, coalesce(sum(p.valor_total), 0) as valor_contratado,
               coalesce(avg(p.valor_total), 0) as ticket_medio
          from rg.v_pedidos p where {PEDIDO_VALIDO} and {filtro_p}""", p)
    kpis.update(cur.fetchone())
    cur.execute(f"""
        select coalesce(sum(greatest(rg.valor_estimado(s.id) - p.valor_total, 0)), 0) as economia,
               coalesce(sum(rg.valor_estimado(s.id)), 0) as estimado_com_pedido
          from rg.v_pedidos p join rg.solicitacoes s on s.id = p.solicitacao_id
         where {PEDIDO_VALIDO} and {filtro_p}""", p)
    kpis.update(cur.fetchone())
    cur.execute("select count(*) as atrasados from rg.v_pedidos p where p.atrasado"
                " and (%(setor)s::text is null or p.setor_codigo = %(setor)s)", p)
    kpis.update(cur.fetchone())
    cur.execute(f"""
        select round(100.0 * count(*) filter (where p.concluido_em::date <= p.data_prevista_entrega) / nullif(count(*), 0))
                 as pontualidade_entregas
          from rg.v_pedidos p where p.status = 'entregue' and {filtro_p}""", p)
    kpis.update(cur.fetchone())
    for chave in ("tempo_aprovacao_dias", "tempo_cotacao_dias", "tempo_ate_pedido_dias", "lead_time_dias",
                  "sla_cumprimento", "valor_contratado", "ticket_medio", "economia", "estimado_com_pedido",
                  "pontualidade_entregas"):
        kpis[chave] = _f(kpis[chave])

    cur.execute(f"""
        select v.status, count(*) as quantidade, coalesce(sum(coalesce(v.valor_final, v.valor_estimado)), 0) as valor
          from rg.v_solicitacoes v where {setor_v} and v.status not in {TERMINAIS}
         group by v.status""", p)
    abertas_status = {r["status"]: {"quantidade": r["quantidade"], "valor": _f(r["valor"])} for r in cur.fetchall()}
    etapas = [
        ("aprovacao", "Aprovação", ("aguardando_gestor", "aguardando_diretoria", "devolvida")),
        ("cotacao", "Cotação", ("aprovada", "em_cotacao")),
        ("fornecedor", "Fornecedor", ("aguardando_pedido",)),
        ("pedido", "Pedido", ("em_pedido",)),
        ("recebimento", "Recebimento", ("recebida_parcial",)),
    ]
    funil = [{"etapa": chave, "rotulo": rotulo,
              "quantidade": sum(abertas_status.get(s, {}).get("quantidade", 0) for s in lista),
              "valor": sum(abertas_status.get(s, {}).get("valor", 0) or 0 for s in lista)}
             for chave, rotulo, lista in etapas]

    cur.execute(f"""
        with meses as (
          select generate_series(date_trunc('month', %(ini)s::date), date_trunc('month', %(fim)s::date),
                                 interval '1 month')::date as mes
        )
        select to_char(m.mes, 'MM/YYYY') as mes,
               (select count(*) from rg.solicitacoes s
                 where date_trunc('month', s.criado_em at time zone %(tz)s)::date = m.mes
                   and (%(setor)s::text is null or s.setor_codigo = %(setor)s)) as solicitacoes,
               (select count(*) from rg.v_pedidos p
                 where {PEDIDO_VALIDO} and date_trunc('month', p.criado_em at time zone %(tz)s)::date = m.mes
                   and (%(setor)s::text is null or p.setor_codigo = %(setor)s)) as pedidos,
               (select coalesce(sum(p.valor_total), 0) from rg.v_pedidos p
                 where {PEDIDO_VALIDO} and date_trunc('month', p.criado_em at time zone %(tz)s)::date = m.mes
                   and (%(setor)s::text is null or p.setor_codigo = %(setor)s)) as valor
          from meses m order by m.mes""", p)
    por_mes = [{**r, "valor": _f(r["valor"])} for r in cur.fetchall()][-24:]

    cur.execute(f"""
        select p.setor_codigo, p.setor_nome, p.setor_cor, count(*) as pedidos, sum(p.valor_total) as valor
          from rg.v_pedidos p where {PEDIDO_VALIDO} and {filtro_p}
         group by p.setor_codigo, p.setor_nome, p.setor_cor order by valor desc""", p)
    por_setor = [{**r, "valor": _f(r["valor"])} for r in cur.fetchall()]

    cur.execute(f"""
        select coalesce(c.nome, 'Itens sem catálogo') as categoria, coalesce(c.cor, '#94A3B8') as cor,
               sum(pi.quantidade * pi.valor_unitario) as valor
          from rg.v_pedidos p
          join rg.pedido_itens pi on pi.pedido_id = p.id
          left join rg.materiais m on m.id = pi.material_id
          left join rg.categorias c on c.id = m.categoria_id
         where {PEDIDO_VALIDO} and {filtro_p}
         group by c.nome, c.cor order by valor desc""", p)
    por_categoria = [{**r, "valor": _f(r["valor"])} for r in cur.fetchall()]

    cur.execute(f"""
        select p.fornecedor_id, coalesce(p.fornecedor_fantasia, p.fornecedor_nome) as fornecedor, p.fornecedor_cnpj as cnpj,
               count(*) as pedidos, sum(p.valor_total) as valor
          from rg.v_pedidos p where {PEDIDO_VALIDO} and {filtro_p}
         group by p.fornecedor_id, p.fornecedor_fantasia, p.fornecedor_nome, p.fornecedor_cnpj
         order by valor desc limit 8""", p)
    top_fornecedores = [{**r, "valor": _f(r["valor"])} for r in cur.fetchall()]

    cur.execute(f"""
        select p.status, count(*) as quantidade, sum(p.valor_total) as valor
          from rg.v_pedidos p where (%(setor)s::text is null or p.setor_codigo = %(setor)s)
           and p.status not in ('entregue', 'reprovado', 'cancelado')
         group by p.status""", p)
    pedidos_abertos = [{**r, "valor": _f(r["valor"])} for r in cur.fetchall()]

    cur.execute(f"""
        select v.comprador_id, v.comprador_nome, count(*) filter (where v.status not in {TERMINAIS}) as em_andamento,
               count(*) filter (where v.pedido_emitido_em is not null) as pedidos,
               avg(extract(epoch from (v.fornecedor_definido_em - v.cotacao_iniciada_em)) / 86400.0)
                 filter (where v.fornecedor_definido_em is not null) as tempo_cotacao_dias
          from rg.v_solicitacoes v where v.comprador_id is not null and {setor_v}
         group by v.comprador_id, v.comprador_nome order by em_andamento desc""", p)
    por_comprador = [{**r, "tempo_cotacao_dias": _f(r["tempo_cotacao_dias"])} for r in cur.fetchall()]

    cur.execute(f"""
        select v.id, v.codigo, v.titulo, v.status, v.urgencia, v.setor_nome, v.setor_cor,
               v.sla_prazo_limite, v.sla_situacao, v.sla_horas_restantes
          from rg.v_solicitacoes v
         where v.status not in {TERMINAIS} and v.sla_concluido_em is null and {setor_v}
         order by v.sla_prazo_limite limit 6""", p)
    criticas = cur.fetchall()

    cur.execute(f"""
        select v.id, v.codigo, v.titulo, v.status, v.setor_nome, v.setor_cor, v.atualizado_em, v.valor_estimado
          from rg.v_solicitacoes v where {setor_v} order by v.atualizado_em desc limit 6""", p)
    recentes = cur.fetchall()

    return {
        "periodo": {"inicio": inicio, "fim": fim, "setor": setor},
        "kpis": kpis, "funil": funil, "por_mes": por_mes, "por_setor": por_setor, "por_categoria": por_categoria,
        "top_fornecedores": top_fornecedores, "pedidos_abertos": pedidos_abertos, "por_comprador": por_comprador,
        "criticas": criticas, "recentes": recentes,
    }
