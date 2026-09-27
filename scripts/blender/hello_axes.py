"""hello_axes.py — smoke test конвейера Blender → glTF → UE (D-018), как hello_krom.py для UE.

    python scripts/bl_run.py scripts/blender/hello_axes.py

Несимметричные метки: куб 2 м в начале, конус на +X 5 м, шар на +Y 3 м, цилиндр на +Z 4 м (у каждого свой
материал-слот). Выгрузка — build/blender/SM_AxisTest.glb, превью — media/renders/blender/hello_axes.png.
Куда метки легли в UE и какой масштаб — проверяет импорт в редакторе (см. scripts/README.md).
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bl_krom as bk  # noqa: E402

bk.reset_scene()
parts = []
bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 1))
parts.append(bk.assign(bpy.context.object, bk.material("wall", (0.62, 0.60, 0.55))))
bpy.ops.mesh.primitive_cone_add(radius1=0.5, depth=1.5, location=(5, 0, 0.75))
parts.append(bk.assign(bpy.context.object, bk.material("gold", (0.60, 0.42, 0.12))))
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, location=(0, 3, 0.5))
parts.append(bk.assign(bpy.context.object, bk.material("dark", (0.03, 0.03, 0.05))))
bpy.ops.mesh.primitive_cylinder_add(radius=0.25, depth=1.0, location=(0, 0, 4.5))
parts.append(bk.assign(bpy.context.object, bk.material("green", (0.10, 0.22, 0.14))))
obj = bk.join(parts, "SM_AxisTest")
bk.export_glb(obj, "SM_AxisTest")
bk.render_preview("hello_axes", eye=(9, -7, 6), target=(1.5, 1, 1))
