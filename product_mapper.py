import pandas as pd

# 加载 mapping 表
df = pd.read_excel("map.xlsx", sheet_name=0)

# 超市简写 -> 表头列名
column_map = {
    "pak": "pak_name",
    "nw": "neww_name",
    "cd": "wool_name"
}

def get_product_id(supermarket: str, name: str, quant: str) -> int | None:
    """
    根据超市名称、商品名（精确匹配）、商品规格，返回商品 ID
    :param supermarket: 'pak' / 'nw' / 'cd'
    :param name: 商品名，必须精确匹配
    :param quant: 规格，例如 '10pack', '700g'
    :return: 对应商品 id 或 None
    """
    col = column_map.get(supermarket.lower())
    if not col:
        raise ValueError("超市名必须是 'pak', 'nw', 'cd' 中之一")

    filtered = df[df[col] == name]
    if filtered.empty:
        return None

    # 在匹配名称的基础上继续匹配规格（quant）
    for _, row in filtered.iterrows():
        if str(row["quant"]).lower() == quant.lower():
            return int(row["id"])

    return None
