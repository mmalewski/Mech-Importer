# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>
#

# Mech Importer 2.0 (Blender Python module)
# https://www.heffaypresents.com/GitHub

import bpy
import types
import bmesh
import math
import mathutils
import array
import os
import time
from bpy_extras.io_utils import unpack_list
from bpy_extras.image_utils import load_image
from progress_report import ProgressReport, ProgressReportSubstep
from bpy.props import (
        BoolProperty,
        FloatProperty,
        StringProperty,
        EnumProperty,
        )
from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        orientation_helper_factory,
        path_reference_mode,
        axis_conversion,
        )

bl_info = {
    "name": "Mech Importer", 
    "category": "Import-Export",
    'author': 'Geoff Gerber',
    'version': (0, 1, 0),
    'blender': (2, 7, 9),
    'description': "Import MWO mechs",
    "location": "File > Import-Export"
    }

# store keymaps here to access after registration
addon_keymaps = []

def strip_slash(line_split):
    if line_split[-1][-1] == 92:  # '\' char
        if len(line_split[-1]) == 1:
            line_split.pop()  # remove the \ item
        else:
            line_split[-1] = line_split[-1][:-1]  # remove the \ from the end last number
        return True
    return False

def import_mech(context, filepath):
    print("Import Mech")
    print(filepath)
    return {'FINISHED'}


class ObjectMoveX(bpy.types.Operator):
    """My Object Moving Script"""      # blender will use this as a tooltip for menu items and buttons.
    bl_idname = "object.move_x"        # unique identifier for buttons and menu items to reference.
    bl_label = "Move X by One"         # display name in the interface.
    bl_options = {'REGISTER', 'UNDO'}  # enable undo for the operator.
    def execute(self, context):        # execute() is called by blender when running the operator.
        # The original script
        scene = context.scene
        for obj in scene.objects:
            obj.location.x += 1.0
        return {'FINISHED'}            # this lets blender know the operator finished successfully.

class ObjectCursorArray(bpy.types.Operator):
    """Object Cursor Array"""
    bl_idname = "object.cursor_array"
    bl_label = "Cursor Array"
    bl_options = {'REGISTER', 'UNDO'}
    total = bpy.props.IntProperty(name="Steps", default=2, min=1, max=100)
    def execute(self, context):
        scene = context.scene
        cursor = scene.cursor_location
        obj = scene.objects.active
        for  i in range(total):
            obj_new = obj.copy()
            scene.objects.link(obj_new)
            factor = i / total
            obj_new.location = (obj.location * factor) + (cursor * (1.0 - factor))
        return {'FINISHED'}

class HelloWorldPanel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_label = "Hello World Panel"
    bl_idname = "OBJECT_PT_hello"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    def draw(self, context):
        layout = self.layout
        obj = context.object
        row = layout.row()
        row.label(text="Hello world!", icon='WORLD_DATA')
        row = layout.row()
        row.label(text="Active object is: " + obj.name)
        row = layout.row()
        row.prop(obj, "name")
        row = layout.row()
        row.operator("mesh.primitive_cube_add")

IOOBJOrientationHelper = orientation_helper_factory("IOOBJOrientationHelper", axis_forward='-Z', axis_up='Y')

class MechImporter(bpy.types.Operator, ImportHelper, IOOBJOrientationHelper):
    """ Create a mech from MWO"""
    bl_idname = "import_scene.mech"
    bl_label = "Import Mech"
    bl_options = {'PRESET', 'UNDO'}
    filename_ext = ".cdf"
    filter_glob = StringProperty(
        default="*.cdf",
        options={'HIDDEN'},
        )

    path_mode = path_reference_mode
    check_extension = True
    def execute(self, context):
        if bpy.data.is_saved and context.user_preferences.filepaths.use_relative_paths:
            import os
            keywords["relpath"] = os.path.dirname(bpy.data.filepath)
        fdir = self.properties.filepath
        print(fdir)
        return import_mech(context, fdir)

    def draw(self, context):
        layout = self.layout

def menu_func_import(self, context):
    self.layout.operator(MechImporter.bl_idname, text="Import Mech")

def menu_func(self, context):
    self.layout.operator(ObjectCursorArray.bl_idname)

def register():
    bpy.utils.register_class(ObjectCursorArray)
    bpy.utils.register_class(ObjectMoveX)
    bpy.utils.register_class(HelloWorldPanel)
    bpy.utils.register_class(MechImporter)
    bpy.types.VIEW3D_MT_object.append(menu_func)
    # handle the keymap
    #wm = bpy.context.window_manager
    #km = wm.keyconfigs.addon.keymaps.new(name='Object Mode', space_type='EMPTY')
    #kmi = km.keymap_items.new(ObjectCursorArray.bl_idname, 'SPACE', 'PRESS', ctrl=True, shift=True)
    #kmi.properties.total = 4
    #addon_keymaps.append(km)
    bpy.types.INFO_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.INFO_MT_file_import.remove(menu_func_import)
    #bpy.types.VIEW3D_MT_object.remove(menu_func)
    #wm = bpy.context.window_manager
    #for km in addon_keymaps:
    #    wm.keyconfigs.addon.keymaps.remove(km)
    # clear the list
    del addon_keymaps[:]
    bpy.utils.unregister_class(ObjectCursorArray) 
    bpy.utils.unregister_class(ObjectMoveX)
    bpy.utils.unregister_class(HelloWorldPanel)
    bpy.utils.unregister_class(MechImporter)

# This allows you to run the script directly from blenders text editor
# to test the addon without having to install it.
if __name__ == "__main__":
    register()


