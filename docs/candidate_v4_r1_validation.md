# 冻结配置回测验证

## 边界

- 固定策略配置；不搜索参数、不按结果改配置。
- 默认验证集为 2017-2024；2026 是 YTD，仅作前瞻观察。
- 2025 被排除，因为该年份已用于问题发现和候选配置形成。
- 所有 Phase2 命令使用 `--no-recompute`，不自动重建因子缓存。

## 年度结果

|   year | sample     | strategy          | go_nogo_overall   | annualized_return   | annualized_excess_return   |   information_ratio | max_drawdown   | avg_turnover   |   n_periods | max_single_period_return   |   max_period_end |
|-------:|:-----------|:------------------|:------------------|:--------------------|:---------------------------|--------------------:|:---------------|:---------------|------------:|:---------------------------|-----------------:|
|   2017 | validation | G_candidate_v4_r1 | GO                | 5.3%                | -13.7%                     |               -2.16 | -8.0%          | 32.5%          |          50 | -3.0%                      |         20171229 |
|   2018 | validation | G_candidate_v4_r1 | GO                | -37.1%              | -12.3%                     |               -0.95 | -35.4%         | 24.3%          |          50 | -10.3%                     |         20181228 |
|   2019 | validation | G_candidate_v4_r1 | GO                | 12.9%               | -18.1%                     |               -2.37 | -18.8%         | 21.6%          |          51 | 7.9%                       |         20191231 |
|   2020 | validation | G_candidate_v4_r1 | GO                | 47.6%               | 16.4%                      |                1.07 | -15.5%         | 24.5%          |          51 | -11.4%                     |         20201231 |
|   2021 | validation | G_candidate_v4_r1 | GO                | -9.5%               | 1.4%                       |                0.1  | -27.1%         | 33.1%          |          51 | -10.8%                     |         20211231 |
|   2022 | validation | G_candidate_v4_r1 | GO                | -20.3%              | 0.2%                       |                0.01 | -27.7%         | 13.1%          |          49 | 5.7%                       |         20221230 |
|   2023 | validation | G_candidate_v4_r1 | GO                | -6.7%               | 9.5%                       |                1.06 | -18.2%         | 10.6%          |          49 | 6.2%                       |         20231229 |
|   2024 | validation | G_candidate_v4_r1 | GO                | 27.6%               | 5.1%                       |                0.38 | -13.5%         | 10.8%          |          51 | 21.5%                      |         20241231 |
|   2026 | ytd        | G_candidate_v4_r1 | NO-GO             | -22.2%              | -26.1%                     |               -2.76 | -9.7%          | 42.2%          |          20 | -6.2%                      |         20260605 |

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
