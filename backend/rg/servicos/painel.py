"""Indicadores do painel executivo. Todas as consultas rodam sob RLS: o gestor vê
apenas o próprio setor, Compras apenas o que foi liberado e o Admin tudo."""
from __future__ import annotations

from datetime import date

TERMINAIS = "('aprovado', 'rejeitado_adm', 'rejeitado_compras', 'cancelado')"


def _float(v):
    return float(v) if v is not None else None


def painel(cur, inicio: date, fim: date, setor: str | None, tz: str) -> dict:
    p = {"ini": inicio, "fim": fim, "setor": setor, "tz": tz}
    filtro = ("(s.criado_em at time zone %(tz)s)::date between %(ini)s and %(fim)s"
              " and (%(setor)s::text is null or s.setor_codigo = %(setor)s)")

    cur.execute(f"""
        select count(*) as total,
               count(*) filter (where s.status not in {TERMINAIS}) as em_andamento,
               count(*) filter (where s.status = 'aprovado') as aprovadas,
               count(*) filter (where s.status in ('rejeitado_adm', 'rejeitado_compras', 'cancelado')) as rejeitadas,
               count(*) filter (where s.status = 'aguardando_adm') as aguardando_adm,
               count(*) filter (where s.status in ('aprovado_adm', 'em_cotacao')) as em_compras,
               count(*) filter (where s.status = 'necessita_nova_cotacao') as nova_cotacao,
               coalesce(sum(s.valor_estimado), 0) as valor_estimado,
               coalesce(sum(s.valor_final_aprovado) filter (where s.status = 'aprovado'), 0) as valor_aprovado,
               coalesce(sum(s.valor_estimado - s.valor_final_aprovado)
                        filter (where s.status = 'aprovado' and s.valor_estimado is not null), 0) as economia,
               avg(case when s.sla_concluido_em <= s.sla_prazo_limite then 1.0 else 0.0 end)
                   filter (where s.status in {TERMINAIS}) as sla_cumprimento,
               avg(extract(epoch from (s.finalizado_em - s.criado_em)) / 86400.0)
                   filter (where s.status in {TERMINAIS}) as ciclo_medio_dias
          from rg.solicitacoes s where {filtro}""", p)
    kpis = cur.fetchone()

    cur.execute(f"""
        select count(*) filter (where v.sla_situacao = 'dentro_prazo') as sla_dentro,
               count(*) filter (where v.sla_situacao = 'alerta') as sla_alerta,
               count(*) filter (where v.sla_situacao = 'estourado') as sla_estourado
          from rg.v_solicitacoes v
         where v.status not in {TERMINAIS} and (%(setor)s::text is null or v.setor_codigo = %(setor)s)""", p)
    kpis.update(cur.fetchone())
    for chave in ("valor_estimado", "valor_aprovado", "economia", "sla_cumprimento", "ciclo_medio_dias"):
        kpis[chave] = _float(kpis[chave])

    cur.execute(f"""
        select s.status, count(*) as quantidade from rg.solicitacoes s where {filtro}
         group by s.status order by quantidade desc""", p)
    por_status = cur.fetchall()

    cur.execute(f"""
        select s.urgencia, count(*) as quantidade from rg.solicitacoes s where {filtro}
         group by s.urgencia order by array_position(array['imediato','urgente','normal'], s.urgencia::text)""", p)
    por_urgencia = cur.fetchall()

    cur.execute(f"""
        select st.codigo as setor_codigo, st.nome as setor_nome, st.cor as setor_cor,
               count(s.id) as quantidade,
               count(s.id) filter (where s.status not in {TERMINAIS}) as em_andamento,
               count(s.id) filter (where s.status = 'aprovado') as aprovadas,
               coalesce(sum(s.valor_final_aprovado) filter (where s.status = 'aprovado'), 0) as valor_aprovado,
               count(s.id) filter (where s.status not in {TERMINAIS} and now() > s.sla_prazo_limite) as sla_estourado
          from rg.solicitacoes s join rg.setores st on st.codigo = s.setor_codigo
         where {filtro}
         group by st.codigo, st.nome, st.cor
         order by quantidade desc, st.nome""", p)
    por_setor = [{**r, "valor_aprovado": _float(r["valor_aprovado"])} for r in cur.fetchall()]

    cur.execute(f"""
        with meses as (
          select generate_series(date_trunc('month', %(ini)s::date), date_trunc('month', %(fim)s::date),
                                 interval '1 month')::date as mes
        )
        select to_char(m.mes, 'MM/YYYY') as mes,
               (select count(*) from rg.solicitacoes s
                 where date_trunc('month', s.criado_em at time zone %(tz)s)::date = m.mes
                   and (%(setor)s::text is null or s.setor_codigo = %(setor)s)) as abertas,
               (select count(*) from rg.solicitacoes s
                 where s.status = 'aprovado' and date_trunc('month', s.finalizado_em at time zone %(tz)s)::date = m.mes
                   and (%(setor)s::text is null or s.setor_codigo = %(setor)s)) as homologadas,
               (select coalesce(sum(s.valor_final_aprovado), 0) from rg.solicitacoes s
                 where s.status = 'aprovado' and date_trunc('month', s.finalizado_em at time zone %(tz)s)::date = m.mes
                   and (%(setor)s::text is null or s.setor_codigo = %(setor)s)) as valor_aprovado
          from meses m order by m.mes""", p)
    por_mes = [{**r, "valor_aprovado": _float(r["valor_aprovado"])} for r in cur.fetchall()][-24:]

    cur.execute(f"""
        select f.razao_social, f.cnpj, count(*) as contratos, sum(s.valor_final_aprovado) as valor
          from rg.solicitacoes s
          join rg.cotacoes c on c.id = s.cotacao_vencedora_id
          join rg.fornecedores f on f.id = c.fornecedor_id
         where s.status = 'aprovado' and {filtro}
         group by f.id, f.razao_social, f.cnpj
         order by valor desc limit 8""", p)
    top_fornecedores = [{**r, "valor": _float(r["valor"])} for r in cur.fetchall()]

    cur.execute(f"""
        select v.id, v.codigo, v.titulo, v.status, v.urgencia, v.setor_nome, v.setor_cor,
               v.sla_prazo_limite, v.sla_situacao, v.sla_horas_restantes
          from rg.v_solicitacoes v
         where v.status not in {TERMINAIS} and (%(setor)s::text is null or v.setor_codigo = %(setor)s)
         order by v.sla_prazo_limite limit 8""", p)
    criticas = cur.fetchall()

    cur.execute("""
        select count(*) filter (where situacao = 'agendado') as agendados,
               count(*) filter (where situacao = 'em_andamento') as em_andamento,
               count(*) filter (where situacao = 'concluido') as concluidos,
               count(*) filter (where situacao = 'cancelado') as cancelados,
               count(*) filter (where atrasado) as atrasados
          from rg.v_servicos
         where data_programada between %(ini)s and %(fim)s
           and (%(setor)s::text is null or setor_codigo = %(setor)s)""", p)
    servicos = cur.fetchone()
    cur.execute("""
        select id, codigo, titulo, categoria, setor_nome, setor_cor, data_programada, hora_inicio, hora_termino,
               situacao, atrasado, responsavel_executor
          from rg.v_servicos
         where situacao in ('agendado', 'em_andamento')
           and data_programada between (now() at time zone %(tz)s)::date - 30 and (now() at time zone %(tz)s)::date + 7
           and (%(setor)s::text is null or setor_codigo = %(setor)s)
         order by atrasado desc, data_programada, hora_inicio limit 8""", p)
    servicos["proximos"] = cur.fetchall()

    return {
        "periodo": {"inicio": inicio, "fim": fim, "setor": setor},
        "kpis": kpis, "por_status": por_status, "por_urgencia": por_urgencia, "por_setor": por_setor,
        "por_mes": por_mes, "top_fornecedores": top_fornecedores, "criticas": criticas, "servicos": servicos,
    }
