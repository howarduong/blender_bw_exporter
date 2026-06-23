# BigWorld Blender Exporter

Blender 3.6 插件：BigWorld 引擎 `.model` / `.visual` / `.primitives` / `.animation` 导入与导出。

**版本：v0.8.0** · Windows x64 · 需要 `bw_export_native.pyd`

---

## 功能

| 能力 | 说明 |
|------|------|
| 静态网格 | 导出 `.model` + `.visual` + `.primitives` |
| 蒙皮网格 | C++ pyd 导出 bind 形三件套 |
| 硬点 | `HP_*` 节点 → 静态含节点导出 |
| 仅动画 | 逐条 Action bake，写入 `.animation` × N（适合大批量 clip） |
| 导入 | 从 `.model` 加载到 Blender 场景 |
| 校验 | 导出前 blocking 检查 |
| 可选 BSP | 静态导出后嵌入 bsp2 |

---

## 系统要求

- **Blender 3.6.x**（内嵌 Python 3.10）
- **Windows x64**
- BigWorld 资源根目录 `game/res`（须含 `resources.xml`）
- **`bw_export_native.pyd`**（见 GitHub Releases 或本地 `lib/win64/`）

---

## 安装

1. 下载本仓库（或 Release 压缩包）。
2. 从 **GitHub Releases** 下载 `bw_export_native.pyd`，放入：

   ```text
   blender_bw_exporter/lib/win64/bw_export_native.pyd
   ```

3. 将整个 **`blender_bw_exporter`** 文件夹复制到 Blender 插件目录：

   ```text
   Blender/3.6/scripts/addons/blender_bw_exporter/
   ```

4. Blender → **编辑 → 偏好设置 → 插件** → 搜索 **BigWorld** → 勾选启用。
5. 插件首选项 → **BW 资源根目录** → 填写 `game/res` 的**绝对路径**（例如 `D:/MyGame/game/res`）。

---

## 推荐工作流（角色 / 大批量动画）

| 步骤 | 导出类型 | 产出 |
|------|----------|------|
| 1 | **蒙皮** | `.model` + `.visual` + `.primitives` |
| 2 | **仅动画** | 同资源目录下 `.animation` × N |
| 3 | Model Editor | 打开 `.model`，从目录加载 / 播放动画 |

蒙皮与动画**硬分离**：先导出 bind 形，再单独导出动画，避免一次性处理全部 clip 导致内存不足。

---

## 导出前检查

- 网格已**三角化**
- 蒙皮：**骨名 = 顶点组名**；Armature 处于 **Rest Position**
- 至少一层 **UV**（勾选 bump 时必需）
- 导出路径须在 `game/res` **子目录**内
- 插件内执行 **校验当前范围**，修复 blocking 错误后再导出

---

## 模型朝向

导出对话框 **「模型朝向」** 指定 Blender 场景轴到 BigWorld 轴的换算：

| 预设 | 前 | 右 | 上 |
|------|-----|-----|-----|
| WoW/管线（默认） | +X | -Y | +Z |
| Blender 默认 | +Y | +X | +Z |
| OpenGL 式 | -Z | +X | +Y |

---

## 菜单入口

- **文件 → 导入/导出 → BigWorld (.model)**
- 侧边栏 **BigWorld** 面板
- 顶栏 **BigWorld** 菜单

导出成功时系统控制台输出 `BW_EXPORT_OK path=...`。

---

## 目录结构

```text
blender_bw_exporter/
├── __init__.py           # 插件入口 (v0.8.0)
├── bw_*.py               # 采集、UI、校验、动画 stream
├── bw_format_core/       # 磁盘格式读写（导入 + .animation 写盘）
├── lib/win64/            # bw_export_native.pyd（Release 提供）
├── README.md
└── CHANGELOG.md
```

---

## 已知限制

- `bw_export_native.pyd` 须单独获取（Release 附件）；无 pyd 时 Export 会报错
- pyd 仅 **Windows x64 / Python 3.10**
- Shell / Portal / Hull 采集尚未实现
- 动画不写回 `.model` 引用列表（Model Editor 可直接加载目录下 `.animation`）

---

## 更新日志

见 [CHANGELOG.md](CHANGELOG.md)
