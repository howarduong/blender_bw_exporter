import bpy

from . import bw_native_bridge
from .bw_export_ui import export_preview_summary


class BW_PT_Sidebar(bpy.types.Panel):
    bl_label = "BigWorld"
    bl_idname = "BW_PT_sidebar"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "BigWorld"

    def draw(self, context):
        layout = self.layout
        props = context.window_manager.bw_export
        scene = context.scene

        icon = "CHECKMARK" if bw_native_bridge.is_available() else "ERROR"
        layout.label(text=bw_native_bridge.status_message(), icon=icon)

        last_path = scene.get("bw_last_export_path", "")
        if last_path:
            layout.label(text=f"上次: {last_path}")

        preview = export_preview_summary(context, props)
        stats = preview["stats"]
        layout.label(
            text=(
                f"预览 · {props.scope} · {preview['config'].pyd_api} · "
                f"网格{stats.mesh_count}"
            ),
            icon="INFO",
        )

        col = layout.column(align=True)
        col.operator("bw.import_model", text="导入 BigWorld…", icon="IMPORT")
        col.operator("bw.export_bigworld", text="导出 BigWorld…", icon="EXPORT")
        col.operator("bw.validate_scene", text="校验当前范围", icon="CHECKMARK")


def register_scene_props() -> None:
    bpy.types.Scene.bw_last_export_path = bpy.props.StringProperty(
        name="上次导出路径",
        default="",
        options={"HIDDEN"},
    )


def unregister_scene_props() -> None:
    del bpy.types.Scene.bw_last_export_path
