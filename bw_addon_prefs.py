import bpy

from . import bw_native_bridge
from .bw_orientation import ORIENTATION_PRESET_ITEMS


class BWAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    bw_res_path: bpy.props.StringProperty(
        name="BW 资源根目录",
        description=(
            "【作用】BigWorld 资源树根路径，对应 BW_RES_PATH，多个路径用分号分隔。"
            "【对齐 Max】BWResource::init 挂载根。"
            "【影响产物】须包含 game/res，否则资源 ID 无法解析。"
        ),
        default="",
    )
    default_export_dir: bpy.props.StringProperty(
        name="默认导出文件夹",
        description="【作用】Export 对话框默认保存文件夹。【影响产物】可使用 Blender 相对路径 //。",
        subtype="DIR_PATH",
        default="//export_bw",
    )
    auto_normalize: bpy.props.BoolProperty(
        name="导出前自动整理场景",
        description="【作用】三角化、权重钳制等。【影响产物】collect 输入质量；非 pyd API。",
        default=True,
    )
    auto_validate: bpy.props.BoolProperty(
        name="导出前自动校验（失败则取消导出）",
        description="【作用】blocking 错误时取消导出。【对齐 Max】validResource 类检查。",
        default=True,
    )
    normalize_skip_skin_transform: bpy.props.BoolProperty(
        name="蒙皮导出不 Apply 物体变换",
        description="【作用】保持 bind 空间。【影响产物】蒙皮 positions 与 bindRow。",
        default=True,
    )
    unit_scale: bpy.props.FloatProperty(
        name="单位缩放",
        description="【作用】写入 pyd unit_scale。【对齐 Max】unitScale。【影响产物】节点 row3、动画位移。",
        default=1.0,
        min=0.0001,
        soft_max=1000.0,
    )
    bone_limit_per_piece: bpy.props.IntProperty(
        name="每块骨骼上限",
        description="【作用】pyd bone_count，超限 split。【默认】17。",
        default=17,
        min=1,
        max=85,
    )
    generate_tangents: bpy.props.BoolProperty(
        name="凹凸贴图 / 切线",
        description="【作用】pyd bump_mapped=true → xyznuvtb。【对齐 Max】bumpMapped。",
        default=True,
    )
    fix_cylindrical: bpy.props.BoolProperty(
        name="圆柱 UV 修复",
        description="【作用】pyd fix_cylindrical → MeshMender。【对齐 Max】fixCylindrical。",
        default=True,
    )
    allow_scale: bpy.props.BoolProperty(
        name="允许缩放",
        description="【作用】pyd allow_scale。【对齐 Max】allowScale。",
        default=False,
    )
    use_legacy_orientation: bpy.props.BoolProperty(
        name="旧版朝向",
        description="【作用】collect 阶段轴约定。【对齐 Max】useLegacyOrientation。",
        default=False,
    )
    default_model_orientation: bpy.props.EnumProperty(
        name="默认模型朝向",
        description="【作用】Export 对话框「模型朝向」的默认值。",
        items=ORIENTATION_PRESET_ITEMS,
        default="WOW_XFNYRZU",
    )

    def get_res_roots(self):
        from .bw_res_path import split_res_roots

        return split_res_roots(self.bw_res_path)

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="路径", icon="FILE_FOLDER")
        box.prop(self, "bw_res_path")
        box.prop(self, "default_export_dir")

        box = layout.box()
        box.label(text="原生模块", icon="EXPORT")
        icon = "CHECKMARK" if bw_native_bridge.is_available() else "ERROR"
        box.label(text=bw_native_bridge.status_message(), icon=icon)

        box = layout.box()
        box.label(text="工作流", icon="MODIFIER")
        box.prop(self, "auto_normalize")
        box.prop(self, "auto_validate")
        box.prop(self, "normalize_skip_skin_transform")

        advanced = layout.box()
        advanced.use_property_split = True
        advanced.label(text="默认导出参数（写入 pyd settings）", icon="PREFERENCES")
        advanced.prop(self, "unit_scale")
        advanced.prop(self, "bone_limit_per_piece")
        advanced.prop(self, "generate_tangents")
        advanced.prop(self, "fix_cylindrical")
        advanced.prop(self, "allow_scale")
        advanced.prop(self, "use_legacy_orientation")
        advanced.prop(self, "default_model_orientation")


def get_prefs(context) -> BWAddonPreferences:
    return context.preferences.addons[__package__].preferences
