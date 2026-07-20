# 冻结配置回测验证

## 边界

- 固定策略配置；不搜索参数、不按结果改配置。
- 默认验证集为 2017-2024；2026 是 YTD，仅作前瞻观察。
- 2025 被排除，因为该年份已用于问题发现和候选配置形成。
- 所有 Phase2 命令使用 `--no-recompute`，不自动重建因子缓存。

## 年度结果

|   year | sample     | strategy            | go_nogo_overall   | annualized_return   | annualized_excess_return   |   information_ratio | max_drawdown   | avg_turnover   |   n_periods | max_single_period_return   |   max_period_end |
|-------:|:-----------|:--------------------|:------------------|:--------------------|:---------------------------|--------------------:|:---------------|:---------------|------------:|:---------------------------|-----------------:|
|   2017 | validation | G_candidate_v4_lite | GO                | 2.1%                | -16.8%                     |               -2.82 | -6.7%          | 36.0%          |          50 | -2.7%                      |         20171229 |
|   2018 | validation | G_candidate_v4_lite | GO                | -33.7%              | -7.2%                      |               -0.55 | -33.2%         | 28.4%          |          50 | -10.3%                     |         20181228 |
|   2019 | validation | G_candidate_v4_lite | GO                | 12.0%               | -18.9%                     |               -2.81 | -18.4%         | 27.7%          |          51 | 7.5%                       |         20191231 |
|   2020 | validation | G_candidate_v4_lite | GO                | 40.9%               | 11.8%                      |                0.82 | -15.4%         | 36.8%          |          51 | -11.6%                     |         20201231 |
|   2021 | validation | G_candidate_v4_lite | GO                | -10.7%              | -0.6%                      |               -0.05 | -23.9%         | 39.4%          |          51 | -10.0%                     |         20211231 |
|   2022 | validation | G_candidate_v4_lite | GO                | -16.7%              | 4.6%                       |                0.32 | -25.3%         | 18.6%          |          49 | 5.9%                       |         20221230 |
|   2023 | validation | G_candidate_v4_lite | GO                | -8.9%               | 7.1%                       |                0.81 | -18.8%         | 13.5%          |          49 | 6.2%                       |         20231229 |
|   2024 | validation | G_candidate_v4_lite | GO                | 23.5%               | 1.6%                       |                0.11 | -13.2%         | 14.9%          |          51 | 20.0%                      |         20241231 |
|   2026 | ytd        | G_candidate_v4_lite | NO-GO             | -23.9%              | -28.2%                     |               -3.62 | -10.4%         | 55.7%          |          20 | -7.6%                      |         20260605 |

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
