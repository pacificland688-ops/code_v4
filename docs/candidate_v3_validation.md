# 冻结配置回测验证

## 边界

- 固定策略配置；不搜索参数、不按结果改配置。
- 默认验证集为 2017-2024；2026 是 YTD，仅作前瞻观察。
- 2025 被排除，因为该年份已用于问题发现和候选配置形成。
- 所有 Phase2 命令使用 `--no-recompute`，不自动重建因子缓存。

## 年度结果

|   year | sample     | strategy       | go_nogo_overall   | annualized_return   | annualized_excess_return   |   information_ratio | max_drawdown   | avg_turnover   |   n_periods | max_single_period_return   |   max_period_end |
|-------:|:-----------|:---------------|:------------------|:--------------------|:---------------------------|--------------------:|:---------------|:---------------|------------:|:---------------------------|-----------------:|
|   2017 | validation | F_candidate_v3 | GO                | 3.7%                | -15.0%                     |               -1.74 | -9.3%          | 36.6%          |          50 | -4.1%                      |         20171229 |
|   2018 | validation | F_candidate_v3 | GO                | -31.2%              | -3.3%                      |               -0.21 | -32.8%         | 29.2%          |          50 | -10.3%                     |         20181228 |
|   2019 | validation | F_candidate_v3 | GO                | 35.8%               | 1.0%                       |                0.12 | -13.8%         | 34.8%          |          51 | 8.5%                       |         20191231 |
|   2020 | validation | F_candidate_v3 | GO                | 37.8%               | 9.3%                       |                0.69 | -17.8%         | 35.5%          |          51 | -11.6%                     |         20201231 |
|   2021 | validation | F_candidate_v3 | GO                | -7.5%               | 5.8%                       |                0.45 | -18.9%         | 35.7%          |          50 | 5.1%                       |         20211231 |
|   2022 | validation | F_candidate_v3 | GO                | -14.3%              | 8.1%                       |                0.57 | -23.7%         | 32.4%          |          49 | 10.5%                      |         20221230 |
|   2023 | validation | F_candidate_v3 | GO                | -18.9%              | -4.4%                      |               -0.5  | -23.9%         | 20.0%          |          49 | 6.5%                       |         20231229 |
|   2024 | validation | F_candidate_v3 | GO                | 17.3%               | -3.7%                      |               -0.28 | -14.2%         | 22.0%          |          51 | 19.6%                      |         20241231 |
|   2026 | ytd        | F_candidate_v3 | NO-GO             | -15.5%              | -18.3%                     |               -1.71 | -6.6%          | 40.2%          |          20 | -5.1%                      |         20260605 |

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
