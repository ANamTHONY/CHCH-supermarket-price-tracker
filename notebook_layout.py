"""Readable notebook cells, preserving SQL tokens and Python execution order."""
import ast
import pprint
import re
import sqlparse

NOTES={
 'silver_v_prices_clean':('清洗规格与计价单位','解析包装规格、识别变重商品、统一每 kg/L/个单价，同时保留原始字段。'),
 'silver_dim_product_source':('维护商品 SKU 映射','按品牌及官网 SKU 维护映射；已确认的映射与待审核状态分别处理。'),
 'silver_fact_product_price':('写入 Silver 价格事实表','按门店、日期与来源 SKU 去重，关联标准商品，原子覆盖生产期事实数据。'),
 'silver_dim_store':('补充门店维度','补入新出现的门店，保留已维护的名称、位置等信息。'),
 'silver_dim_date':('补充日期维度','为报价日期生成日期维度，已有日期不重复插入。'),
 'gold_v_analysis_products':('分析商品清单','列出已选定的肉、蛋、奶分析商品与映射覆盖。'),
 'gold_v_analysis_prices':('生成可比报价视图','只选择分析商品，并根据价格、规格、单位和映射状态判断是否可比。'),
 'gold_v_unmapped_products':('未映射商品汇总','保留尚未关联标准商品的报价，便于后续补映射。'),
 'silver_v_product_mapping_queue':('生成待映射清单','按来源 SKU 汇总待审核商品、规范规格、官网链接与审核原因。'),
 'silver_v_price_quality':('生成数据质量汇总','按日期、品牌和类别统计缺价、未知单位、规格和映射情况。'),
}

def code(text):
    ast.parse(text)
    return {'cell_type':'code','metadata':{},'source':text.splitlines(True),'execution_count':None,'outputs':[]}

def significant(sql):
    return [(str(kind),value) for kind,value in sqlparse.lexer.tokenize(sql) if kind not in sqlparse.tokens.Whitespace]

def sql_cell(sql):
    formatted=sqlparse.format(sql,reindent_aligned=True,indent_width=4).strip()
    formatted=formatted.replace(' AS WITH ', ' AS\nWITH ')
    if significant(formatted)!=significant(sql):
        raise ValueError('SQL formatter changed non-whitespace tokens')
    if '"""' in formatted:raise ValueError('Unexpected triple quote in SQL')
    # Raw string preserves the SQL regex backslashes exactly.
    text='spark.sql(r"""\n'+formatted+'\n""")\n'
    argument=ast.parse(text).body[0].value.args[0].value
    if significant(argument)!=significant(sql):raise ValueError('SQL string escaping changed')
    return code(text)

def title(sql):
    match=re.search(r'(?:INTO|TABLE(?: IF NOT EXISTS)?|VIEW|UPDATE)\s+workspace\.default\.(\w+)',sql,re.I)
    target=match.group(1) if match else 'SQL'
    if 'pending_review' in sql and sql.lstrip().startswith('UPDATE'):
        return '隔离存在歧义的 SKU','暂缓映射两种身份尚未确认的 1L 牛奶 SKU，避免错误合并。'
    if 'Reviewed exact source' in sql:
        return '应用已核实的 SKU 映射','根据已核实的品牌、规格和商品身份补充映射。'
    return NOTES.get(target,(f'{target} · {sql.split()[0]}','执行下方 SQL，按 Run all 的顺序处理。'))

def readable_cells(cells):
    out=[];step=0
    for cell in cells:
        if cell['cell_type']!='code':out.append(cell);continue
        text=''.join(cell['source'])
        tree=ast.parse(text)
        assignment=next((n for n in tree.body if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('statements','refresh_statements') and isinstance(n.value,ast.List)),None)
        if assignment is None:
            out.append(cell);continue
        name=assignment.targets[0].id
        loop=next((n for n in tree.body if isinstance(n,ast.For) and isinstance(n.iter,ast.Name) and n.iter.id==name),None)
        if loop is None:raise ValueError('SQL list has no execution loop')
        if ast.dump(ast.parse('for statement in '+name+':\n    spark.sql(statement)').body[0],include_attributes=False)!=ast.dump(loop,include_attributes=False):
            raise ValueError('Unexpected SQL loop logic; cannot flatten safely')
        lines=text.splitlines(True)
        before=''.join(lines[:assignment.lineno-1]+lines[assignment.end_lineno:loop.lineno-1]).strip()
        after=''.join(lines[loop.end_lineno:]).strip()
        if before:
            # Expand the migration dictionary without rewriting any other Python.
            for node in ast.parse(before).body:
                if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='MIGRATIONS':
                    fragment=ast.get_source_segment(before,node)
                    before=before.replace(fragment,'MIGRATIONS = '+pprint.pformat(ast.literal_eval(node.value),width=90,sort_dicts=False),1)
                    break
            out.append(code(before+'\n'))
        for sql in ast.literal_eval(assignment.value):
            step+=1;heading,note=title(sql)
            out.append({'cell_type':'markdown','metadata':{},'source':[f'## {step:02d} · {heading}\n','\n',note+'\n']})
            out.append(sql_cell(sql))
        if after:
            out.append({'cell_type':'markdown','metadata':{},'source':['## 检查结果\n','\n','查看处理结果及质量检查；运行失败时先查看对应步骤的报错。\n']})
            out.append(code(after+'\n'))
    return out
