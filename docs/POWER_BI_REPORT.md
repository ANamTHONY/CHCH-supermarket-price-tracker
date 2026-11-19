# Power BI report and methodology

Updated: **19 November 2026**. This describes the latest development report.
The older `POWER_BI_PLAN.md` is retained as design history, not current acceptance
criteria. No report screenshots, PBIX file or raw price history are supplied here.

## Scope

- Collection starts on 27 October 2026, using Pacific/Auckland collection dates.
- Coverage targets 28 Christchurch stores: 11 New World, 5 PAK'nSAVE and 12 Woolworths.
- Broad egg, milk and meat listings support the store map. The curated product
  comparison and weekday views use 15 selected products, with eligibility varying
  by store and date. These are different analysis populations.
- Cross-chain equivalence must be checked separately. In particular, meat cuts,
  specifications and units are not automatically interchangeable.

## Report pages

### Where to shop

The Azure Maps view compares stores within each supermarket chain. Users choose
the chain and switch between a relative price index and promotion coverage.
The store comparison SQL is [powerbi_store_value_map.sql](../powerbi_store_value_map.sql).

- The price index compares a store's SKU price with the same-day, same-chain,
  same-SKU and pack median, then averages eligible ratios. At least two valid
  store prices are required. An index of 100 means the peer median, not a
  national benchmark. A different assortment can still affect store averages.
- The promotion share uses SKUs with valid prices and known promotion flags
  across all target stores in the chain on that day. It is not a discount amount.
- Map ranking is within chain; it is not a direct ranking of all three chains.

The accompanying weekday chart asks **Which day offers better value?** It plots
Monday to Sunday in separate chain panels. A store selection can narrow the
analysis through the shared store dimension; otherwise it summarizes the selected
chain. It uses the historical metric below, not the map's same-day price index.

### Find stores near you

The second page combines an ArcGIS store map, a category/product/pack selector,
today's store price table and a seven-day product price trend. The table presents
both pack price and normalized unit price, plus the recorded promotion flag.
The trend needs an unambiguous product and store context; missing observations
must not be filled with zero or represented as today's prices.

ArcGIS region selection helps explore nearby stores, but dynamic highlighting of
the cheapest store inside an arbitrary circle is not a completed feature. Public
ArcGIS embedding also remains unresolved. These limitations are separate from
the underlying price calculations.

## Price definition: include lower member prices

For all three chains, the intended effective price is the lowest available
positive regular or member price. A missing, zero or higher member price must
not replace a valid regular price. The corresponding normalized unit-price
fields follow the same rule. Preserve the original fields for auditability.

For `FactPriceAll`, create these calculated columns before the daily value table:

```dax
Effective Price =
VAR R = FactPriceAll[total_price]
VAR M = FactPriceAll[member_price]
RETURN IF ( M > 0 && NOT ( R > 0 ), M,
    IF ( R > 0, IF ( M > 0, MIN ( R, M ), R ) ) )
```

```dax
Effective Unit Price =
VAR R = FactPriceAll[normalized_unit_price]
VAR M = FactPriceAll[normalized_member_unit_price]
RETURN IF ( M > 0 && NOT ( R > 0 ), M,
    IF ( R > 0, IF ( M > 0, MIN ( R, M ), R ) ) )
```

Member eligibility still applies. The report must say that prices include member
offers, rather than imply every shopper can pay them without membership.
An `is_promo` flag alone does not measure a price reduction: the lower offer may
be stored separately in `member_price` while the regular price stays unchanged.

## Weekday metric: Low Price Share

This answers: **How often were eligible tracked products below their own recent
usual price?** It does not answer which chain has the lowest absolute prices.

1. Start from `FactPriceAll`, which includes the tracked products without filtering
   out zero cross-store price gaps. The older price-gap-only fact table is unsuitable.
2. Build one daily unit price for the same store, product, source SKU, pack and
   normalized unit. Exclude conflicting daily prices and ambiguous product variants.
3. Calculate the median over the preceding 28 calendar days, excluding the current
   day, for that same identity. Require at least seven prior observed days.
4. Mark the current price as low only when it is strictly below that median,
   comparing prices rounded to six decimal places. Insufficient history is excluded,
   not counted as a non-discounted observation.
5. Average eligible product flags within each store/day; then average stores within
   each date and dates within the chosen weekday. This avoids simply weighting a
   store more heavily because it contributes more rows.

Create the calculated table `ProductValueDaily` using the expression in
[powerbi_product_value_daily.dax](../powerbi_product_value_daily.dax).
Add single-direction, many-to-one relationships to `DimDate[calendar_date]`,
`DimStore[store_key]` and `DimProduct[product_id]` using the corresponding columns.
Sort `weekday_name` by `weekday_number` (Monday = 1).

Create these measures individually:

```dax
Low Price Share =
AVERAGEX (
    VALUES ( ProductValueDaily[collected_date] ),
    CALCULATE (
        AVERAGEX (
            VALUES ( ProductValueDaily[store_key] ),
            CALCULATE ( AVERAGE ( ProductValueDaily[low_price_flag] ) )
        )
    )
)
```

```dax
Observed Days = DISTINCTCOUNT ( ProductValueDaily[collected_date] )
```

```dax
Comparable Products per Store Day =
AVERAGEX (
    SUMMARIZE ( ProductValueDaily,
        ProductValueDaily[collected_date], ProductValueDaily[store_key] ),
    CALCULATE ( DISTINCTCOUNT ( ProductValueDaily[product_id] ) )
)
```

Format Low Price Share as a percentage. Use weekday on X, Low Price Share on Y,
chain as small multiples, and both sample measures in tooltips. Do not apply an
only-today page filter to this historical chart. Store and date dimension keys
must match the calculated table's data types and grain.

## Interpretation and remaining validation

The report suggests cross-store consistency for observed Woolworths products,
store differences at New World and PAK'nSAVE, and a lower Friday low-price share
in some chain panels. These are early, sample-specific observations. Uniform
prices between stores do not mean constant prices over time, and lower Low Price
Share does not necessarily mean a more expensive shopping basket.

The 28-day baseline is a lookback limit, not proof of 28 observed dates. Eligibility
further reduces the short collection history. Repeated store/product rows are
correlated and cannot substitute for additional independent weeks. A persistent
discount can also become the new median and stop counting as low without its
price rising. Missing or changing product coverage can shift the result.

Before making weekday recommendations, accumulate more complete weeks, show
sample counts, examine a stable product/store panel and compare alternative
baselines. There is no supported general recommendation to avoid Friday.

The repository contains selected analysis assets, not a complete PBIP export.
Reconstruction requires the documented dimensions and fact tables. Reconcile the
map SQL, imported queries and price measures after changes; old price-gap filters
must not silently exclude products from full-price or historical views. Refresh
the imported semantic model after source updates and verify refresh history.
