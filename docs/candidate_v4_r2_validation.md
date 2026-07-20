# 冻结配置回测验证

## 边界

- 固定策略配置；不搜索参数、不按结果改配置。
- 默认验证集为 2017-2024；2026 是 YTD，仅作前瞻观察。
- 2025 被排除，因为该年份已用于问题发现和候选配置形成。
- 所有 Phase2 命令使用 `--no-recompute`，不自动重建因子缓存。

## 年度结果

|   year | sample     | strategy          | go_nogo_overall   | annualized_return   | annualized_excess_return   |   information_ratio | max_drawdown   | avg_turnover   |   n_periods | max_single_period_return   |   max_period_end |
|-------:|:-----------|:------------------|:------------------|:--------------------|:---------------------------|--------------------:|:---------------|:---------------|------------:|:---------------------------|-----------------:|
|   2017 | validation | G_candidate_v4_r2 | GO                | 2.1%                | -17.0%                     |               -2.66 | -5.5%          | 13.7%          |          50 | -2.9%                      |         20171229 |
|   2018 | validation | G_candidate_v4_r2 | GO                | -27.5%              | 1.3%                       |                0.25 | -30.8%         | 12.0%          |          50 | -8.7%                      |         20181228 |
|   2019 | validation | G_candidate_v4_r2 | GO                | 14.3%               | -17.2%                     |               -2.48 | -12.5%         | 13.1%          |          51 | 6.5%                       |         20191231 |
|   2020 | validation | G_candidate_v4_r2 | GO                | 6.6%                | -17.0%                     |               -1.43 | -18.2%         | 19.5%          |          51 | -12.1%                     |         20201231 |
|   2021 | validation | G_candidate_v4_r2 | GO                | -15.2%              | -6.9%                      |               -0.64 | -24.6%         | 15.9%          |          51 | 5.5%                       |         20211231 |
|   2022 | validation | G_candidate_v4_r2 | GO                | -16.0%              | 4.9%                       |                0.37 | -20.6%         | 14.0%          |          49 | 4.6%                       |         20221230 |
|   2023 | validation | G_candidate_v4_r2 | GO                | -1.3%               | 15.0%                      |                1.81 | -14.6%         | 13.6%          |          49 | 5.8%                       |         20231229 |
|   2024 | validation | G_candidate_v4_r2 | GO                | 26.5%               | 3.9%                       |                0.3  | -11.2%         | 13.6%          |          51 | 21.2%                      |         20241231 |
|   2026 | ytd        | G_candidate_v4_r2 | NO-GO             | 7.0%                | 5.9%                       |                0.64 | -8.8%          | 11.6%          |          20 | -6.4%                      |         20260605 |

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
