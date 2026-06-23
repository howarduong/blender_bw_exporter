import os

import bpy
from bpy_extras.io_utils import ExportHelper, ImportHelper

from . import bw_native_bridge
from .bw_addon_prefs import get_prefs
from .bw_collect import resolved_kind_to_export_type
from .bw_console import info_en
from .bw_coordinate import coordinate_converter_scope, resolve_orientation_converter
from .bw_import_scene import import_ir_to_scene
from .bw_export_ui import (
    EXPORT_KIND_ANIM_ONLY,
    EXPORT_KIND_INFER,
    animation_preview_label,
    count_scope_stats,
    output_description,
    pyd_stats_animation_label,
    pyd_stats_summary_label,
    resolve_export_config,
    should_show_anim_box,
    should_show_mesh_options,
    should_show_reembed_bsp,
    should_show_snap_vertices,
    export_preview_summary,
)
from .bw_res_path import resolve_export_paths
from .bw_validate import validate_export


class BW_OT_ImportModel(bpy.types.Operator, ImportHelper):
    bl_idname = "bw.import_model"
    bl_label = "导入 BigWorld"
    bl_description = "从 .model 导入 mesh、材质与骨架到 Blender 场景"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".model"
    filter_glob: bpy.props.StringProperty(default="*.model", options={"HIDDEN"})

    def draw(self, context):
        props = context.window_manager.bw_export
        layout = self.layout
        box = layout.box()
        box.label(text="模型朝向 (BW → Blender)", icon="ORIENTATION_GIMBAL")
        box.prop(props, "model_orientation", text="朝向预设")
        if props.model_orientation == "CUSTOM":
            col = box.column(align=True)
            col.prop(props, "custom_forward", text="前")
            col.prop(props, "custom_right", text="右")
            col.prop(props, "custom_up", text="上")

    def execute(self, context):
        prefs = get_prefs(context)
        props = context.window_manager.bw_export
        try:
            converter = resolve_orientation_converter(
                props.model_orientation,
                custom_forward=props.custom_forward,
                custom_right=props.custom_right,
                custom_up=props.custom_up,
            )
        except ValueError as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        try:
            from .bw_format_core import load

            with coordinate_converter_scope(converter):
                ir = load(self.filepath, prefs.get_res_roots())
                import_ir_to_scene(ir, context)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            info_en(f"BW_ERR_IMPORT {exc}")
            return {"CANCELLED"}

        info_en(f"BW_IMPORT_OK path={self.filepath} orientation={converter.preset_id}")
        self.report({"INFO"}, f"已导入 {os.path.basename(self.filepath)}")
        return {"FINISHED"}

    def invoke(self, context, event):
        prefs = get_prefs(context)
        props = context.window_manager.bw_export
        props.model_orientation = prefs.default_model_orientation
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class BW_OT_ExportBigWorld(bpy.types.Operator, ExportHelper):
    bl_idname = "bw.export_bigworld"
    bl_label = "导出 BigWorld"
    bl_description = "采集场景并写出 .model / .visual / .primitives 或逐条 .animation"
    bl_options = {"REGISTER"}

    filename_ext = ".model"
    filter_glob: bpy.props.StringProperty(default="*.model", options={"HIDDEN"})

    @staticmethod
    def _export_props(context):
        return context.window_manager.bw_export

    def draw(self, context):
        props = self._export_props(context)
        prefs = get_prefs(context)
        layout = self.layout
        preview = export_preview_summary(context, props, self.filepath)
        config = preview["config"]
        stats = preview["stats"]

        path_box = layout.box()
        path_box.label(text="路径", icon="FILE")
        path_box.prop(self, "filepath", text="保存为")

        if self.filepath:
            base = os.path.splitext(os.path.basename(self.filepath))[0]
            model_abs, res_root, prefix, under = resolve_export_paths(
                self.filepath,
                prefs.get_res_roots(),
                base,
            )
            path_box.label(text=f"资源 ID  {prefix}")
            path_box.label(text=f"res 根  {res_root}")
            if not under:
                path_box.label(
                    text="路径不在 BW 资源根下，请保存到 game/res 子目录",
                    icon="ERROR",
                )
            del model_abs

        main_box = layout.box()
        main_box.prop(props, "scope", text="导出范围")
        main_box.prop(props, "export_kind", text="导出类型")
        if props.export_kind == EXPORT_KIND_INFER:
            main_box.label(
                text=f"自动推断 → {preview['inferred_label']}  ({config.pyd_api})",
                icon="INFO",
            )
        else:
            api_label = config.pyd_api
            if config.resolved_kind == EXPORT_KIND_ANIM_ONLY:
                api_label = "Python stream_animations"
            main_box.label(text=f"路径: {api_label}", icon="INFO")

        if should_show_anim_box(config):
            anim_box = layout.box()
            header = anim_box.row()
            header.prop(
                props,
                "show_anim_settings",
                icon="TRIA_DOWN" if props.show_anim_settings else "TRIA_RIGHT",
                emboss=False,
                text="动画设置",
            )
            if props.show_anim_settings:
                anim_box.prop(props, "animation_sample_mode", text="采样")
                anim_box.prop(props, "export_all_actions")
                if config.resolved_kind == EXPORT_KIND_ANIM_ONLY:
                    has_actions = (
                        stats.armature_count > 0
                        and (
                            props.export_all_actions and len(bpy.data.actions) > 0
                            or not props.export_all_actions
                            and stats.action_candidate_count > 0
                        )
                    )
                    anim_box.label(
                        text=animation_preview_label(
                            stats,
                            export_all_actions=props.export_all_actions,
                        ),
                        icon="INFO" if has_actions else "ERROR",
                    )

        if should_show_mesh_options(config):
            opt_box = layout.box()
            header = opt_box.row()
            header.prop(
                props,
                "show_mesh_options",
                icon="TRIA_DOWN" if props.show_mesh_options else "TRIA_RIGHT",
                emboss=False,
                text="本次选项",
            )
            if props.show_mesh_options:
                opt_box.prop(props, "keep_existing_materials")
                if should_show_snap_vertices(config):
                    opt_box.prop(props, "snap_vertices")
                if should_show_reembed_bsp(config):
                    opt_box.prop(props, "reembed_bsp")

        orient_box = layout.box()
        orient_header = orient_box.row()
        orient_header.prop(
            props,
            "show_orientation_settings",
            icon="TRIA_DOWN" if props.show_orientation_settings else "TRIA_RIGHT",
            emboss=False,
            text="模型朝向 (collect → BW 轴)",
        )
        if props.show_orientation_settings:
            orient_box.prop(props, "model_orientation", text="朝向预设")
            if props.model_orientation == "CUSTOM":
                col = orient_box.column(align=True)
                col.prop(props, "custom_forward", text="前")
                col.prop(props, "custom_right", text="右")
                col.prop(props, "custom_up", text="上")
            try:
                from .bw_orientation import resolve_orientation_converter

                summary = resolve_orientation_converter(
                    props.model_orientation,
                    custom_forward=props.custom_forward,
                    custom_right=props.custom_right,
                    custom_up=props.custom_up,
                ).summary
                orient_box.label(text=summary, icon="ORIENTATION_GIMBAL")
            except ValueError as exc:
                orient_box.label(text=str(exc), icon="ERROR")

        summary_box = layout.box()
        summary_box.label(text="导出预览", icon="INFO")
        summary_box.label(text=f"将调用 {config.pyd_api}")
        anim_summary = pyd_stats_summary_label(config, stats)
        if anim_summary:
            anim_part = anim_summary
        else:
            anim_part = pyd_stats_animation_label(stats)
        summary_box.label(
            text=(
                f"网格 {stats.mesh_count} · 蒙皮 {stats.skinned_mesh_count} · "
                f"骨架 {stats.armature_count} · {anim_part}"
            )
        )
        summary_box.label(text=f"产出 {preview['output_description']}")

    def execute(self, context):
        props = self._export_props(context)
        prefs = get_prefs(context)

        validation = validate_export(context, props, self.filepath, prefs)
        for warning in validation.warnings:
            self.report({"WARNING"}, warning)
            info_en(f"BW_WARN {warning}")
        if prefs.auto_validate and not validation.ok:
            for err in validation.errors:
                self.report({"ERROR"}, err)
                info_en(f"BW_ERR {err}")
            return {"CANCELLED"}

        config = resolve_export_config(context, props)
        if config.resolved_kind != EXPORT_KIND_ANIM_ONLY and not bw_native_bridge.is_available():
            msg = bw_native_bridge.status_message()
            self.report({"ERROR"}, msg)
            info_en(f"BW_ERR {msg}")
            return {"CANCELLED"}

        base = os.path.splitext(os.path.basename(self.filepath))[0]
        model_abs, res_root, prefix, _under = resolve_export_paths(
            self.filepath,
            prefs.get_res_roots(),
            base,
        )
        export_type = resolved_kind_to_export_type(config.resolved_kind)
        export_stats = count_scope_stats(
            context,
            props.scope,
            export_all_actions=props.export_all_actions,
        )

        try:
            out_path, mesh_count, warnings = bw_native_bridge.export_asset(
                context=context,
                model_path=model_abs,
                resource_prefix=prefix,
                res_root=res_root,
                export_type=export_type,
                scope=props.scope,
                keep_existing_materials=props.keep_existing_materials,
                bump_mapped=prefs.generate_tangents,
                fix_cylindrical=prefs.fix_cylindrical,
                bone_count=prefs.bone_limit_per_piece,
                allow_scale=prefs.allow_scale,
                snap_vertices=props.snap_vertices,
                use_legacy_orientation=prefs.use_legacy_orientation,
                unit_scale=prefs.unit_scale,
                export_all_actions=props.export_all_actions,
                animation_sample_mode=props.animation_sample_mode,
                resolved_kind=config.resolved_kind,
                model_orientation=props.model_orientation,
                custom_forward=props.custom_forward,
                custom_right=props.custom_right,
                custom_up=props.custom_up,
            )
        except Exception as exc:
            message = str(exc)
            self.report({"ERROR"}, message)
            info_en(f"BW_ERR_EXPORT {message}")
            return {"CANCELLED"}

        for warning in warnings:
            self.report({"WARNING"}, warning)
            info_en(f"BW_WARN {warning}")

        if props.reembed_bsp and config.resolved_kind not in (
            "ANIM_ONLY",
            "SKINNED",
        ):
            try:
                bw_native_bridge.embed_bsp_for_visual(res_root, prefix)
                info_en(f"BSP re-embedded for {prefix}")
            except Exception as exc:
                message = str(exc)
                self.report({"WARNING"}, f"bsp 嵌入失败: {message}")
                info_en(f"BW_WARN embed_bsp {message}")

        context.scene.bw_last_export_path = out_path
        info_en(
            f"BW_EXPORT_OK path={out_path} meshes={mesh_count} api={config.pyd_api}"
        )
        self.report(
            {"INFO"},
            f"已导出 {output_description(config, export_stats)} → {out_path}",
        )
        return {"FINISHED"}

    def invoke(self, context, event):
        prefs = get_prefs(context)
        props = self._export_props(context)
        props.model_orientation = prefs.default_model_orientation
        if prefs.default_export_dir:
            self.filepath = prefs.default_export_dir
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}


class BW_OT_ValidateScene(bpy.types.Operator):
    bl_idname = "bw.validate_scene"
    bl_label = "校验场景"
    bl_description = "检查路径、骨架、材质等；blocking 错误阻止导出"

    def execute(self, context):
        props = context.window_manager.bw_export
        prefs = get_prefs(context)
        filepath = context.scene.get("bw_last_export_path") or prefs.default_export_dir
        if not filepath or not filepath.endswith(".model"):
            filepath = os.path.join(
                bpy.path.abspath(prefs.default_export_dir or "//"),
                "export.model",
            )

        validation = validate_export(context, props, filepath, prefs)
        for warning in validation.warnings:
            self.report({"WARNING"}, warning)
        if validation.ok:
            self.report({"INFO"}, "校验通过，可以导出")
            info_en("BW_VALIDATE_OK")
            return {"FINISHED"}
        for err in validation.errors:
            self.report({"ERROR"}, err)
        info_en("BW_VALIDATE_FAIL")
        return {"CANCELLED"}
