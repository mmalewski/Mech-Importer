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
import bpy.types
import bpy.utils
import types
import bmesh
import math
import mathutils
import array
import os
import time
import xml.etree as etree
import xml.etree.ElementTree as ET
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
weapons = [ "hero","missile","narc","uac", "uac2", "uac5", "uac10", "uac20", 
           "ac2","ac5","ac10","ac20","gauss","ppc","flamer","_mg_","lbx",
           "laser","ams","phoenix","blank","invasion", "hmg", "lmg", "lams" ]
materials = {}      # All the materials found for the mech
cockpit_materials = {}

def strip_slash(line_split):
    if line_split[-1][-1] == 92:  # '\' char
        if len(line_split[-1]) == 1:
            line_split.pop()  # remove the \ item
        else:
            line_split[-1] = line_split[-1][:-1]  # remove the \ from the end last number
        return True
    return False

def get_base_dir(filepath):
    return os.path.abspath(os.path.join(os.path.dirname(filepath), os.pardir, os.pardir, os.pardir))

def get_body_dir(filepath):
    return os.path.join(os.path.dirname(filepath), "body")

def get_mech(filepath):
    return os.path.splitext(os.path.basename(filepath))[0]

def import_armature(rig):
    bpy.ops.wm.collada_import(filepath=rig, find_chains=True,auto_connect=True)

def create_materials(matfile, basedir):
    materials = {}
    mats = ET.parse(matfile)
    for mat in mats.iter("Material"):
        if "Name" in mat.attrib:
            # An actual material.  Create the material, set to nodes, clear and rebuild using the info from the material XML file.
            name = mat.attrib["Name"]
            matname = bpy.data.materials.new(mat.attrib["Name"])
            materials[name] = matname
            print("Found material: " + matname.name)
            matname.use_nodes = True
            tree_nodes = matname.node_tree
            links = tree_nodes.links

            for n in tree_nodes.nodes:
                tree_nodes.nodes.remove(n)

            # Every material will have a PrincipledBSDF and Material output.  Add, place, and link.
            shaderPrincipledBSDF = tree_nodes.nodes.new('ShaderNodeBsdfPrincipled')
            shaderPrincipledBSDF.location =  300,500
            shout=tree_nodes.nodes.new('ShaderNodeOutputMaterial')
            shout.location = 500,500
            links.new(shaderPrincipledBSDF.outputs[0], shout.inputs[0])
            # For each Texture element, add the file and plug in to the appropriate slot on the PrincipledBSDF shader
            for texture in mat.iter("Texture"):
                print("Adding texture " + texture.attrib["Map"])
                if texture.attrib["Map"] == "Diffuse":
                    texturefile = os.path.normpath(os.path.join(basedir, os.path.splitext(texture.attrib["File"])[0] + ".dds"))
                    if os.path.isfile(texturefile):
                        matDiffuse = bpy.data.images.load(filepath=texturefile, check_existing=True)
                        shaderDiffImg = tree_nodes.nodes.new('ShaderNodeTexImage')
                        shaderDiffImg.image=matDiffuse
                        shaderDiffImg.location = 0,600
                        links.new(shaderDiffImg.outputs[0], shaderPrincipledBSDF.inputs[0])
                if texture.attrib["Map"] == "Specular":
                    texturefile = os.path.normpath(os.path.join(basedir, os.path.splitext(texture.attrib["File"])[0] + ".dds"))
                    if os.path.isfile(texturefile):
                        matSpec=bpy.data.images.load(filepath=texturefile, check_existing=True)
                        shaderSpecImg=tree_nodes.nodes.new('ShaderNodeTexImage')
                        shaderSpecImg.color_space = 'NONE'
                        shaderSpecImg.image=matSpec
                        shaderSpecImg.location = 0,325
                        links.new(shaderSpecImg.outputs[0], shaderPrincipledBSDF.inputs[5])
                if texture.attrib["Map"] == "Bumpmap":
                    if os.path.isfile(texturefile):
                        texturefile = os.path.normpath(os.path.join(basedir, os.path.splitext(texture.attrib["File"])[0] + ".dds"))
                        matNormal=bpy.data.images.load(filepath=texturefile, check_existing=True)
                        shaderNormalImg=tree_nodes.nodes.new('ShaderNodeTexImage')
                        shaderNormalImg.color_space = 'NONE'
                        shaderNormalImg.image=matNormal
                        shaderNormalImg.location = -100,0
                        converterNormalMap=tree_nodes.nodes.new('ShaderNodeNormalMap')
                        converterNormalMap.location = 100,0
                        links.new(shaderNormalImg.outputs[0], converterNormalMap.inputs[1])
                        links.new(converterNormalMap.outputs[0], shaderPrincipledBSDF.inputs[17])
    return materials

def import_geometry(cdffile, basedir, bodydir, mechname):
    print("Importing mech geometry...")
    geometry = ET.parse(cdffile)
    for geo in geometry.iter("Attachment"):
        if not geo.attrib["AName"] == "cockpit":
            print("Importing " + geo.attrib["AName"])
            # Get all the attribs
            aname = geo.attrib["AName"]
            rotation = geo.attrib["Rotation"].split(',')
            position = geo.attrib["Position"].split(',')
            bonename = geo.attrib["BoneName"].replace(' ','_')
            binding = os.path.join(basedir, os.path.splitext(geo.attrib["Binding"])[0] + ".dae")
            flags = geo.attrib["Flags"]
            # Materials depend on the part type.  For most, <mech>_body.  Weapons is <mech>_variant.  Window/cockpit is 
            # <mech>_window.
            materialname = mechname + "_body"
            if any(weapon in aname for weapon in weapons):
                materialname = mechname + "_variant"
            if "head_cockpit" in aname:
                materialname = mechname + "_window"
                print("material name:" + materialname)
            # We now have all the geometry parts that need to be imported, their loc/rot, and material.  Import.
            bpy.ops.wm.collada_import(filepath=binding,find_chains=True,auto_connect=True)
            obj_objects = bpy.context.selected_objects[:]
            i = 0
            #for obj in obj_objects:
            #    obj.select = False
            for obj in obj_objects:
                bpy.context.scene.objects.active = obj
                print("Name: " + obj.name)
                if i == 0:
                    bpy.context.active_object.rotation_mode = 'QUATERNION'
                    bpy.context.active_object.rotation_quaternion.w = float(rotation[0])
                    bpy.context.active_object.rotation_quaternion.x = float(rotation[1])
                    bpy.context.active_object.rotation_quaternion.y = float(rotation[2])
                    bpy.context.active_object.rotation_quaternion.z = float(rotation[3])
                    bpy.context.active_object.location.x = float(position[0])
                    bpy.context.active_object.location.y = float(position[1])
                    bpy.context.active_object.location.z = float(position[2])
                    i = i + 1
            
                if not obj.type == 'EMPTY':
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.object.vertex_group_add()
                    bpy.context.object.vertex_groups.active.name = bonename
                    bpy.ops.mesh.select_all(action='SELECT')
                    bpy.ops.mesh.select_all(action='TOGGLE')
                    bpy.ops.object.mode_set(mode='OBJECT')
                    bpy.context.object.data.materials.append(bpy.data.materials[0])               # If there is no material, add a dummy mat.
                    bpy.context.object.data.materials[0] = materials[materialname]
                obj.select = False

def import_mech(context, filepath, *, use_dds=True, use_tif=False):
    print("Import Mech")
    print(filepath)
    cdffile = filepath      # The input file
    # Split up filepath into the variables we want.
    basedir = get_base_dir(filepath)
    bodydir = get_body_dir(filepath)
    mechdir = os.path.dirname(filepath)
    mech = get_mech(filepath)
    matfile = os.path.join(bodydir, mech + "_body.mtl")
    cockpit_matfile = os.path.join(mechdir, "cockpit_standard", mech + "_a_cockpit_standard.mtl")
    print("Material file: " + matfile)
    print("Cockpit material file: " + cockpit_matfile)
    bpy.context.scene.render.engine = 'CYCLES'      # Set to cycles mode
    import_armature(os.path.join(bodydir, mech + ".dae"))   # import the armature.
    # Create the materials.
    materials = create_materials(matfile, basedir)
    cockpit_materials = create_materials(cockpit_matfile, basedir)
    geometry = import_geometry(cdffile, basedir, bodydir, mech)
    return {'FINISHED'}

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

    texture_type = EnumProperty(
        name="Texture Type",
        description = "Identify the type of texture file imported into the Texture nodes.",
        items = (('ON', "DDS", "Reference DDS files for textures."),
                 ('OFF', "TIF", "Reference TIF files for textures."),
                 ),
        )

    path_mode = path_reference_mode
    check_extension = True
    def execute(self, context):
        if self.texture_type == 'OFF':
            self.use_tif = False
        else:
            self.use_dds = False
        keywords = {}
        if bpy.data.is_saved and context.user_preferences.filepaths.use_relative_paths:
            import os
            keywords["relpath"] = os.path.dirname(bpy.data.filepath)
        fdir = self.properties.filepath
        #keywords["cdffile"] = fdir
        return import_mech(context, fdir, **keywords)

    def draw(self, context):
        layout = self.layout

        row = layout.row(align = True)
        box = layout.box()
        box.label("Select texture type")
        row = box.row()
        row.prop(self, "texture_type", expand = True)


def menu_func_import(self, context):
    self.layout.operator(MechImporter.bl_idname, text="Import Mech")

def menu_func(self, context):
    self.layout.operator(ObjectCursorArray.bl_idname)

def register():
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
    bpy.utils.unregister_class(MechImporter)

# This allows you to run the script directly from blenders text editor
# to test the addon without having to install it.
if __name__ == "__main__":
    register()


