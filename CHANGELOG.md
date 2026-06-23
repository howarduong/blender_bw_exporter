# Changelog

## [0.8.0] - 2026-06-20

### Added

- 静态 / 蒙皮 / 仅动画 / 导入 / Validate 完整工作流
- Python `stream_animation_clips` 逐条写 `.animation`（支持数百 clip，防 OOM）
- WoW 轴预设、Export 对话框、N 面板、顶栏菜单
- 可选 BSP 嵌入（`embed_bsp_for_visual`）
- 损坏或超大帧范围 Action 在 discover 阶段跳过（`BW_WARN`）

### Changed

- 蒙皮与动画硬分离：`export_animated` 不写 `.animation`
- 移除 pyd 大批量动画路径与 model 合并 UI

### Removed

- `bw_merge_animations.py`（Model Editor 可直接加载 `.animation`）

---

## [0.7.x]

- 蒙皮 / stream 动画分离
- 导出时 discover clip；逐条 `Stream N/M` 日志

---

## [0.6.x]

- 基础 Export UI 与 pyd 桥接
