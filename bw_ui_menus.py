import bpy


def menu_import(self, context):
    self.layout.operator("bw.import_model", text="BigWorld (.model)")


def menu_export(self, context):
    self.layout.operator("bw.export_bigworld", text="BigWorld (.model)")


def menu_topbar(self, context):
    self.layout.menu("TOPBAR_MT_bigworld", icon="WORLD")


class TOPBAR_MT_bigworld(bpy.types.Menu):
    bl_label = "BigWorld"
    bl_description = "BigWorld 导入 / 导出 / 校验"

    def draw(self, context):
        layout = self.layout
        layout.operator("bw.import_model", text="导入 BigWorld (.model)...", icon="IMPORT")
        layout.operator("bw.export_bigworld", text="导出 BigWorld (.model)...", icon="EXPORT")
        layout.separator()
        layout.operator("bw.validate_scene", text="校验当前范围", icon="CHECKMARK")


def register_menus() -> None:
    bpy.utils.register_class(TOPBAR_MT_bigworld)
    bpy.types.TOPBAR_MT_file_import.append(menu_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_export)
    bpy.types.TOPBAR_MT_editor_menus.append(menu_topbar)


def unregister_menus() -> None:
    bpy.types.TOPBAR_MT_editor_menus.remove(menu_topbar)
    bpy.types.TOPBAR_MT_file_export.remove(menu_export)
    bpy.types.TOPBAR_MT_file_import.remove(menu_import)
    bpy.utils.unregister_class(TOPBAR_MT_bigworld)
