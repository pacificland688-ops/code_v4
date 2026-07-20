# 冻结配置回测验证

## 边界

- 固定策略配置；不搜索参数、不按结果改配置。
- 默认验证集为 2017-2024；2026 是 YTD，仅作前瞻观察。
- 2025 被排除，因为该年份已用于问题发现和候选配置形成。
- 所有 Phase2 命令使用 `--no-recompute`，不自动重建因子缓存。

## 年度结果

|   year | sample     | strategy       | go_nogo_overall   | annualized_return   | annualized_excess_return   |   information_ratio | max_drawdown   | avg_turnover   |   n_periods | max_single_period_return   |   max_period_end |
|-------:|:-----------|:---------------|:------------------|:--------------------|:---------------------------|--------------------:|:---------------|:---------------|------------:|:---------------------------|-----------------:|
|   2017 | validation | E_candidate_v2 | GO                | 2.9%                | -15.8%                     |               -1.83 | -9.2%          | 36.8%          |          50 | -4.5%                      |         20171229 |
|   2018 | validation | E_candidate_v2 | GO                | -31.0%              | -3.1%                      |               -0.19 | -32.3%         | 27.8%          |          50 | -10.2%                     |         20181228 |
|   2019 | validation | E_candidate_v2 | GO                | 31.2%               | -2.5%                      |               -0.29 | -15.0%         | 34.7%          |          51 | 8.8%                       |         20191231 |
|   2020 | validation | E_candidate_v2 | GO                | 37.0%               | 8.6%                       |                0.66 | -17.7%         | 36.8%          |          51 | -11.6%                     |         20201231 |
|   2021 | validation | E_candidate_v2 | GO                | -8.6%               | 4.6%                       |                0.35 | -20.0%         | 32.8%          |          50 | 5.1%                       |         20211231 |
|   2022 | validation | E_candidate_v2 | GO                | -15.2%              | 7.2%                       |                0.5  | -24.4%         | 31.7%          |          49 | 11.2%                      |         20221230 |
|   2023 | validation | E_candidate_v2 | GO                | -19.6%              | -5.3%                      |               -0.65 | -24.0%         | 24.2%          |          49 | 6.4%                       |         20231229 |
|   2024 | validation | E_candidate_v2 | GO                | 17.7%               | -3.3%                      |               -0.25 | -14.0%         | 21.9%          |          51 | 20.0%                      |         20241231 |
|   2026 | ytd        | E_candidate_v2 | NO-GO             | -15.3%              | -18.1%                     |               -1.68 | -6.6%          | 40.4%          |          20 | -5.1%                      |         20260605 |

## 相对差异

|   year | sample     |
|-------:|:-----------|
|   2017 | validation |
|   2018 | validation |
|   2019 | validation |
|   2020 | validation |
|   2021 | validation |
|   2022 | validation |
|   2023 | validation |
|   2024 | validation |
|   2026 | ytd        |

## 初步判读

- 判读统计已排除 `NO_GO_DATA_INVALID` 记录。
- 判读规则：只有跨多数验证年改善、且 2026 YTD 不明显反向，才进入更细的交易成本/持仓归因；否则保留诊断，不升级为生产候选。
