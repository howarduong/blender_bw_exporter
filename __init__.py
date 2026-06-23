bl_info = {
    "name": "BigWorld 导出器",
    "author": "BigWorld Team",
    "version": (0, 8, 0),
    "blender": (3, 6, 0),
    "location": "文件 > 导入/导出 BigWorld；顶栏 > BigWorld",
    "description": "BigWorld .model 导入/导出 — 蒙皮 pyd + 逐条动画",
    "category": "Import-Export",
}

import bpy

from . import (
    bw_addon_prefs,
    bw_native_bridge,
    bw_operators,
    bw_ui_menus,
    bw_ui_panel,
    bw_ui_properties,
)

classes = (
    bw_addon_prefs.BWAddonPreferences,
    bw_ui_properties.BWExportProperties,
    bw_operators.BW_OT_ImportModel,
    bw_operators.BW_OT_ExportBigWorld,
    bw_operators.BW_OT_ValidateScene,
    bw_ui_panel.BW_PT_Sidebar,
)


def _safe_register_class(cls):
    try:
        bpy.utils.unregister_class(cls)
    except RuntimeError:
        pass
    bpy.utils.register_class(cls)


def register():
    bw_native_bridge.reset_native_probe()
    for cls in classes:
        _safe_register_class(cls)
    bw_ui_properties.register_properties()
    bw_ui_panel.register_scene_props()
    bw_ui_menus.register_menus()


def unregister():
    bw_ui_menus.unregister_menus()
    bw_ui_panel.unregister_scene_props()
    bw_ui_properties.unregister_properties()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
