import bpy

from .bw_orientation import AXIS_ENUM_ITEMS, ORIENTATION_PRESET_ITEMS

SCOPE_ITEMS = [
    (
        "SELECTED",
        "选中及子级",
        "导出当前选中对象及其全部子孙（适合多 Geoset 角色）",
    ),
    (
        "VISIBLE",
        "可见对象",
        "导出视口中未隐藏的对象",
    ),
    (
        "SCENE",
        "整个场景",
        "导出场景中全部相关对象",
    ),
]

EXPORT_KIND_ITEMS = [
    (
        "INFER",
        "自动推断",
        "根据 Armature、HP_* 等选择 export_static / export_animated",
    ),
    (
        "STATIC",
        "静态",
        "pyd export_static，export_mode=STATIC",
    ),
    (
        "STATIC_NODES",
        "静态（含硬点）",
        "pyd export_static，export_mode=STATIC_WITH_NODES；采集 HP_* 与 nodes[]",
    ),
    (
        "SKINNED",
        "蒙皮",
        "pyd export_animated",
    ),
    (
        "ANIM_ONLY",
        "仅动画",
        "Python 逐条写 .animation；需已有 .visual",
    ),
]

ANIM_SAMPLE_ITEMS = [
    (
        "KEYFRAMES",
        "仅关键帧",
        "只采样各 Action 的关键帧时间（大量 clip 时快很多）",
    ),
    (
        "EVERY_FRAME",
        "逐帧",
        "按 Action 有效帧范围内每一帧采样",
    ),
]


class BWExportProperties(bpy.types.PropertyGroup):
    scope: bpy.props.EnumProperty(
        name="导出范围",
        description="【作用】collect 对象集合。【推荐】角色用「选中及子级」。",
        items=SCOPE_ITEMS,
        default="SELECTED",
    )
    export_kind: bpy.props.EnumProperty(
        name="导出类型",
        description="【作用】选择 pyd API：静态 / 蒙皮 / 仅动画等。",
        items=EXPORT_KIND_ITEMS,
        default="INFER",
    )
    animation_sample_mode: bpy.props.EnumProperty(
        name="动画采样",
        description="【作用】帧范围自动来自 Action 关键帧；此处只控制采样密度。",
        items=ANIM_SAMPLE_ITEMS,
        default="KEYFRAMES",
    )
    export_all_actions: bpy.props.BoolProperty(
        name="导出文件内全部 Action",
        description="【作用】扫描 bpy.data.actions 中目标骨架的全部 clip；【关闭】仅当前/NLA。",
        default=True,
    )
    keep_existing_materials: bpy.props.BoolProperty(
        name="保留已有 .visual 材质",
        description="【作用】pyd keep_existing_materials。【场景】重导已存在 .visual。",
        default=False,
    )
    snap_vertices: bpy.props.BoolProperty(
        name="顶点对齐 (snap)",
        description="【作用】pyd snap_vertices。【仅】静态类导出。",
        default=False,
    )
    reembed_bsp: bpy.props.BoolProperty(
        name="重新嵌入 bsp2 碰撞",
        description="【作用】导出后调 embed_bsp_for_visual。【场景】修复已有资产碰撞。",
        default=False,
    )
    show_anim_settings: bpy.props.BoolProperty(
        name="动画设置",
        description="展开动画设置区域",
        default=True,
    )
    show_mesh_options: bpy.props.BoolProperty(
        name="本次选项",
        description="展开本次导出选项区域",
        default=True,
    )
    show_orientation_settings: bpy.props.BoolProperty(
        name="模型朝向",
        description="展开 Blender 模型朝向设置",
        default=True,
    )
    model_orientation: bpy.props.EnumProperty(
        name="模型朝向",
        description=(
            "【作用】collect 将 Blender 矩阵/向量换算为 BigWorld 轴系后再交给 pyd。"
            "【场景】不同 DCC 导入的角色轴向不同，导出前按场景实际前/右/上选择。"
        ),
        items=ORIENTATION_PRESET_ITEMS,
        default="WOW_XFNYRZU",
    )
    custom_forward: bpy.props.EnumProperty(
        name="前 (Forward)",
        description="自定义：Blender 世界中模型“向前”的轴",
        items=AXIS_ENUM_ITEMS,
        default="POS_X",
    )
    custom_right: bpy.props.EnumProperty(
        name="右 (Right)",
        description="自定义：Blender 世界中模型“向右”的轴",
        items=AXIS_ENUM_ITEMS,
        default="NEG_Y",
    )
    custom_up: bpy.props.EnumProperty(
        name="上 (Up)",
        description="自定义：Blender 世界中模型“向上”的轴",
        items=AXIS_ENUM_ITEMS,
        default="POS_Z",
    )


def register_properties() -> None:
    bpy.types.WindowManager.bw_export = bpy.props.PointerProperty(type=BWExportProperties)


def unregister_properties() -> None:
    del bpy.types.WindowManager.bw_export
