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
from math import radians

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
# There are misspelled words (missle).  Just an FYI.
weapons = [ "hero","missile", "missle", "narc","uac", "uac2", "uac5", "uac10", "uac20", "rac",
           "ac2","ac5","ac10","ac20","gauss","ppc","flamer","_mg_","_lbx", "damaged", "_mount",
           "laser","ams","_phoenix","blank","invasion", "hmg", "lmg", "lams", "hand", "barrel" ]
materials = {}      # All the materials found for the mech
cockpit_materials = {}
WGT_PREFIX = "WGT-"  # Prefix for widget objects
ROOT_NAME = "Bip01"   # Name of the root bone.
WGT_LAYERS = [x == 19 for x in range(0, 20)]  # Widgets go on the last scene layer.

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

def get_scaling_factor(o):
    # Calculate the scaling factor that should get applied to bone shapes, so they are
    # relatively close in size to the mech they are on.  Locust is 7.4, DWF is 12.9
    local_bbox_center = 0.125 * sum((Vector(b) for b in o.bound_box), Vector())
    global_bbox_center = o.matrix_world * local_bbox_center
    return global_bbox_center[2]/7.4

def convert_to_rotation(rotation):
    tmp = rotation.split(',')
    w = float(tmp[0])
    x = float(tmp[1])
    y = float(tmp[2])
    z = float(tmp[3])
    return mathutils.Quaternion((w,x,y,z))

def convert_to_location(location):
    tmp = location.split(',')
    x = float(tmp[0])
    y = float(tmp[1])
    z = float(tmp[2])
    return mathutils.Vector((x,y,z))

def get_transform_matrix(rotation, location):
    # Given a location Vector and a Quaternion rotation, get the 4x4 transform matrix.  Assumes scale is 1.
    mat_location = mathutils.Matrix.Translation(location)
    mat_rotation = mathutils.Matrix.Rotation(rotation.angle, 4, rotation.axis)
    mat_scale = mathutils.Matrix.Scale(1, 4, (0.0, 0.0, 1.0))  # Identity matrix
    mat_out = mat_location * mat_rotation * mat_scale
    return mat_out

def import_armature(rig):
    try:
        bpy.ops.wm.collada_import(filepath=rig, find_chains=True,auto_connect=True)
        armature = bpy.data.objects['Armature']
        bpy.context.scene.objects.active = armature
        bpy.ops.object.mode_set(mode='EDIT')
        amt=armature.data
        armature.show_x_ray = True
        armature.data.show_axes = True
        armature.data.draw_type = 'BBONE'
        armature.draw_type = 'WIRE'
    except:
        #File not found
        return False
    return True

def obj_to_bone(obj, rig, bone_name):
    # From Rigify.  Used for widget creation
    """ Places an object at the location/rotation/scale of the given bone.
    """
    if bpy.context.mode == 'EDIT_ARMATURE':
        raise MetarigError("obj_to_bone(): does not work while in edit mode")
    bone = rig.data.bones[bone_name]
    mat = rig.matrix_world * bone.matrix_local
    obj.location = mat.to_translation()
    obj.rotation_mode = 'XYZ'
    obj.rotation_euler = mat.to_euler()
    scl = mat.to_scale()
    scl_avg = (scl[0] + scl[1] + scl[2]) / 3
    obj.scale = (bone.length * scl_avg), (bone.length * scl_avg), (bone.length * scl_avg)

def copy_bone(obj, bone_name, assign_name=''):
    """ From metarig
        Makes a copy of the given bone in the given armature object.
        Returns the resulting bone's name.
    """
    #if bone_name not in obj.data.bones:
    if bone_name not in obj.data.edit_bones:
        raise MetarigError("copy_bone(): bone '%s' not found, cannot copy it" % bone_name)

    if obj == bpy.context.active_object and bpy.context.mode == 'EDIT_ARMATURE':
        if assign_name == '':
            assign_name = bone_name
        # Copy the edit bone
        edit_bone_1 = obj.data.edit_bones[bone_name]
        edit_bone_2 = obj.data.edit_bones.new(assign_name)
        bone_name_1 = bone_name
        bone_name_2 = edit_bone_2.name

        edit_bone_2.parent = edit_bone_1.parent
        edit_bone_2.use_connect = edit_bone_1.use_connect

        # Copy edit bone attributes
        edit_bone_2.layers = list(edit_bone_1.layers)

        edit_bone_2.head = mathutils.Vector(edit_bone_1.head)
        edit_bone_2.tail = mathutils.Vector(edit_bone_1.tail)
        edit_bone_2.roll = edit_bone_1.roll

        edit_bone_2.use_inherit_rotation = edit_bone_1.use_inherit_rotation
        edit_bone_2.use_inherit_scale = edit_bone_1.use_inherit_scale
        edit_bone_2.use_local_location = edit_bone_1.use_local_location

        edit_bone_2.use_deform = edit_bone_1.use_deform
        edit_bone_2.bbone_segments = edit_bone_1.bbone_segments
        edit_bone_2.bbone_in = edit_bone_1.bbone_in
        edit_bone_2.bbone_out = edit_bone_1.bbone_out

        bpy.ops.object.mode_set(mode='OBJECT')

        # Get the pose bones
        pose_bone_1 = obj.pose.bones[bone_name_1]
        pose_bone_2 = obj.pose.bones[bone_name_2]

        # Copy pose bone attributes
        pose_bone_2.rotation_mode = pose_bone_1.rotation_mode
        pose_bone_2.rotation_axis_angle = tuple(pose_bone_1.rotation_axis_angle)
        pose_bone_2.rotation_euler = tuple(pose_bone_1.rotation_euler)
        pose_bone_2.rotation_quaternion = tuple(pose_bone_1.rotation_quaternion)

        pose_bone_2.lock_location = tuple(pose_bone_1.lock_location)
        pose_bone_2.lock_scale = tuple(pose_bone_1.lock_scale)
        pose_bone_2.lock_rotation = tuple(pose_bone_1.lock_rotation)
        pose_bone_2.lock_rotation_w = pose_bone_1.lock_rotation_w
        pose_bone_2.lock_rotations_4d = pose_bone_1.lock_rotations_4d

        # Copy custom properties
        for key in pose_bone_1.keys():
            if key != "_RNA_UI" \
            and key != "rigify_parameters" \
            and key != "rigify_type":
                prop1 = rna_idprop_ui_prop_get(pose_bone_1, key, create=False)
                prop2 = rna_idprop_ui_prop_get(pose_bone_2, key, create=True)
                pose_bone_2[key] = pose_bone_1[key]
                for key in prop1.keys():
                    prop2[key] = prop1[key]

        bpy.ops.object.mode_set(mode='EDIT')

        return bone_name_2
    else:
        raise MetarigError("Cannot copy bones outside of edit mode")

def flip_bone(obj, bone_name):
    """ Flips an edit bone.
    """
    if bone_name not in obj.data.bones:
        raise MetarigError("flip_bone(): bone '%s' not found, cannot copy it" % bone_name)

    if obj == bpy.context.active_object and bpy.context.mode == 'EDIT_ARMATURE':
        bone = obj.data.edit_bones[bone_name]
        head = mathutils.Vector(bone.head)
        tail = mathutils.Vector(bone.tail)
        bone.tail = head + tail
        bone.head = tail
        bone.tail = head
    else:
        raise MetarigError("Cannot flip bones outside of edit mode")

def create_materials(matfile, basedir):
    materials = {}
    mats = ET.parse(matfile)
    for mat in mats.iter("Material"):
        if "Name" in mat.attrib:
            # An actual material.  Create the material, set to nodes, clear and rebuild using the info from the material XML file.
            name = mat.attrib["Name"]
            matname = bpy.data.materials.new(mat.attrib["Name"])
            materials[name] = matname
            #print("Found material: " + matname.name)
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
                #print("Adding texture " + texture.attrib["Map"])
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

def create_widget(rig, bone_name, bone_transform_name=None):
    # From Rigify utils.py
    """ Creates an empty widget object for a bone, and returns the object.
    """
    if bone_transform_name is None:
        bone_transform_name = bone_name
    obj_name = WGT_PREFIX + rig.name + '_' + bone_name
    scene = bpy.context.scene
    id_store = bpy.context.window_manager
    # Check if it already exists in the scene
    if obj_name in scene.objects:
        # Move object to bone position, in case it changed
        obj = scene.objects[obj_name]
        obj_to_bone(obj, rig, bone_transform_name)
        return None
    else:
        # Delete object if it exists in blend data but not scene data.
        # This is necessary so we can then create the object without
        # name conflicts.
        if obj_name in bpy.data.objects:
            bpy.data.objects[obj_name].user_clear()
            bpy.data.objects.remove(bpy.data.objects[obj_name])
        # Create mesh object
        mesh = bpy.data.meshes.new(obj_name)
        obj = bpy.data.objects.new(obj_name, mesh)
        scene.objects.link(obj)
        # Move object to bone position and set layers
        obj_to_bone(obj, rig, bone_transform_name)
        wgts_group_name = 'WGTS_' + rig.name
        if wgts_group_name in bpy.data.objects.keys():
            obj.parent = bpy.data.objects[wgts_group_name]
        obj.layers = WGT_LAYERS
        return obj

def create_hand_widget(rig, bone_name, size=1.0, bone_transform_name=None):
    # Create hand widget.  From Rigify's widgets.py
    obj = create_widget(rig, bone_name, bone_transform_name)
    if obj is not None:
        verts = [(0.0*size, 1.5*size, -0.7000000476837158*size), (1.1920928955078125e-07*size, -0.25*size, -0.6999999284744263*size), 
                 (0.0*size, -0.25*size, 0.7000000476837158*size), (-1.1920928955078125e-07*size, 1.5*size, 0.6999999284744263*size), 
                 (5.960464477539063e-08*size, 0.7229999899864197*size, -0.699999988079071*size), (-5.960464477539063e-08*size, 0.7229999899864197*size, 0.699999988079071*size), 
                 (1.1920928955078125e-07*size, -2.9802322387695312e-08*size, -0.699999988079071*size), (0.0*size, 2.9802322387695312e-08*size, 0.699999988079071*size), ]
        edges = [(1, 2), (0, 3), (0, 4), (3, 5), (4, 6), (1, 6), (5, 7), (2, 7)]
        faces = []

        mesh = obj.data
        mesh.from_pydata(verts, edges, faces)
        mesh.update()

        mod = obj.modifiers.new("subsurf", 'SUBSURF')
        mod.levels = 2
        return obj
    else:
        return None

def create_foot_widget(rig, bone_name, size=1.0, bone_transform_name=None):
    # Create hand widget.  From Rigify's widgets.py
    obj = create_widget(rig, bone_name, bone_transform_name)
    if obj is not None:
        verts = [(-0.6999998688697815*size, -0.5242648720741272*size, 0.0*size), (-0.7000001072883606*size, 1.2257349491119385*size, 0.0*size), 
                 (0.6999998688697815*size, 1.2257351875305176*size, 0.0*size), (0.7000001072883606*size, -0.5242648720741272*size, 0.0*size), 
                 (-0.6999998688697815*size, 0.2527350187301636*size, 0.0*size), (0.7000001072883606*size, 0.2527352571487427*size, 0.0*size), 
                 (-0.7000001072883606*size, 0.975735068321228*size, 0.0*size), (0.6999998688697815*size, 0.9757352471351624*size, 0.0*size), ]
        edges = [(1, 2), (0, 3), (0, 4), (3, 5), (4, 6), (1, 6), (5, 7), (2, 7), ]
        faces = []

        mesh = obj.data
        mesh.from_pydata(verts, edges, faces)
        mesh.update()

        mod = obj.modifiers.new("subsurf", 'SUBSURF')
        mod.levels = 2
        return obj
    else:
        return None

def create_cube_widget(rig, bone_name, radius=0.5, bone_transform_name=None):
    """ Creates a basic cube widget.
    """
    obj = create_widget(rig, bone_name, bone_transform_name)
    if obj is not None:
        r = radius
        verts = [(r, r, r), (r, -r, r), (-r, -r, r), (-r, r, r), (r, r, -r), (r, -r, -r), (-r, -r, -r), (-r, r, -r)]
        edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
        mesh = obj.data
        mesh.from_pydata(verts, edges, [])
        mesh.update()

def create_circle_widget(rig, bone_name, radius=1.0, head_tail=0.0, with_line=False, bone_transform_name=None):
    """ Creates a basic circle widget, a circle around the y-axis.
        radius: the radius of the circle
        head_tail: where along the length of the bone the circle is (0.0=head, 1.0=tail)
    """
    obj = create_widget(rig, bone_name, bone_transform_name)
    if obj != None:
        v = [(0.7071068286895752, 2.980232238769531e-07, -0.7071065306663513), (0.8314696550369263, 2.980232238769531e-07, -0.5555699467658997), (0.9238795042037964, 2.682209014892578e-07, -0.3826831877231598), (0.9807852506637573, 2.5331974029541016e-07, -0.19509011507034302), (1.0, 2.365559055306221e-07, 1.6105803979371558e-07), (0.9807853698730469, 2.2351741790771484e-07, 0.19509044289588928), (0.9238796234130859, 2.086162567138672e-07, 0.38268351554870605), (0.8314696550369263, 1.7881393432617188e-07, 0.5555704236030579), (0.7071068286895752, 1.7881393432617188e-07, 0.7071070075035095), (0.5555702447891235, 1.7881393432617188e-07, 0.8314698934555054), (0.38268327713012695, 1.7881393432617188e-07, 0.923879861831665), (0.19509008526802063, 1.7881393432617188e-07, 0.9807855486869812), (-3.2584136988589307e-07, 1.1920928955078125e-07, 1.000000238418579), (-0.19509072601795197, 1.7881393432617188e-07, 0.9807854294776917), (-0.3826838731765747, 1.7881393432617188e-07, 0.9238795638084412), (-0.5555707216262817, 1.7881393432617188e-07, 0.8314695358276367), (-0.7071071863174438, 1.7881393432617188e-07, 0.7071065902709961), (-0.8314700126647949, 1.7881393432617188e-07, 0.5555698871612549), (-0.923879861831665, 2.086162567138672e-07, 0.3826829195022583), (-0.9807853698730469, 2.2351741790771484e-07, 0.1950896978378296), (-1.0, 2.365559907957504e-07, -7.290432222362142e-07), (-0.9807850122451782, 2.5331974029541016e-07, -0.195091113448143), (-0.9238790273666382, 2.682209014892578e-07, -0.38268423080444336), (-0.831468939781189, 2.980232238769531e-07, -0.5555710196495056), (-0.7071058750152588, 2.980232238769531e-07, -0.707107424736023), (-0.555569052696228, 2.980232238769531e-07, -0.8314701318740845), (-0.38268208503723145, 2.980232238769531e-07, -0.923879861831665), (-0.19508881866931915, 2.980232238769531e-07, -0.9807853102684021), (1.6053570561780361e-06, 2.980232238769531e-07, -0.9999997615814209), (0.19509197771549225, 2.980232238769531e-07, -0.9807847142219543), (0.3826850652694702, 2.980232238769531e-07, -0.9238786101341248), (0.5555717945098877, 2.980232238769531e-07, -0.8314683437347412)]
        verts = [(a[0] * radius, head_tail, a[2] * radius) for a in v]
        if with_line:
            edges = [(28, 12), (0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (9, 10), (10, 11), (11, 12), (12, 13), (13, 14), (14, 15), (15, 16), (16, 17), (17, 18), (18, 19), (19, 20), (20, 21), (21, 22), (22, 23), (23, 24), (24, 25), (25, 26), (26, 27), (27, 28), (28, 29), (29, 30), (30, 31), (0, 31)]
        else:
            edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (9, 10), (10, 11), (11, 12), (12, 13), (13, 14), (14, 15), (15, 16), (16, 17), (17, 18), (18, 19), (19, 20), (20, 21), (21, 22), (22, 23), (23, 24), (24, 25), (25, 26), (26, 27), (27, 28), (28, 29), (29, 30), (30, 31), (0, 31)]
        mesh = obj.data
        mesh.from_pydata(verts, edges, [])
        mesh.update()
        return obj
    else:
        return None

def create_compass_widget(rig, bone_name, bone_transform_name=None):
    # From Rigify
    """ Creates a compass-shaped widget.
    """
    obj = create_widget(rig, bone_name, bone_transform_name)
    if obj != None:
        verts = [(0.0, 1.2000000476837158, 0.0), (0.19509032368659973, 0.9807852506637573, 0.0), (0.3826834559440613, 0.9238795042037964, 0.0), 
                 (0.5555702447891235, 0.8314695954322815, 0.0), (0.7071067690849304, 0.7071067690849304, 0.0), (0.8314696550369263, 0.5555701851844788, 0.0), 
                 (0.9238795042037964, 0.3826834261417389, 0.0), (0.9807852506637573, 0.19509035348892212, 0.0), (1.2000000476837158, 7.549790126404332e-08, 0.0), 
                 (0.9807853102684021, -0.19509020447731018, 0.0), (0.9238795638084412, -0.38268327713012695, 0.0), (0.8314696550369263, -0.5555701851844788, 0.0), 
                 (0.7071067690849304, -0.7071067690849304, 0.0), (0.5555701851844788, -0.8314696550369263, 0.0), (0.38268327713012695, -0.9238796234130859, 0.0), 
                 (0.19509008526802063, -0.9807853102684021, 0.0), (-3.2584136988589307e-07, -1.2999999523162842, 0.0), (-0.19509072601795197, -0.9807851910591125, 0.0), 
                 (-0.3826838731765747, -0.9238793253898621, 0.0), (-0.5555707216262817, -0.8314692974090576, 0.0), (-0.7071072459220886, -0.707106351852417, 0.0), 
                 (-0.8314700126647949, -0.5555696487426758, 0.0), (-0.923879861831665, -0.3826826810836792, 0.0), (-0.9807854294776917, -0.1950894594192505, 0.0), 
                 (-1.2000000476837158, 9.655991561885457e-07, 0.0), (-0.980785071849823, 0.1950913518667221, 0.0), (-0.923879086971283, 0.38268446922302246, 0.0), 
                 (-0.831468939781189, 0.5555712580680847, 0.0), (-0.7071058750152588, 0.707107663154602, 0.0), (-0.5555691123008728, 0.8314703702926636, 0.0), 
                 (-0.38268208503723145, 0.9238801002502441, 0.0), (-0.19508881866931915, 0.9807855486869812, 0.0)]
        edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (9, 10), (10, 11), (11, 12), (12, 13), (13, 14), (14, 15), (15, 16), (16, 17), 
                 (17, 18), (18, 19), (19, 20), (20, 21), (21, 22), (22, 23), (23, 24), (24, 25), (25, 26), (26, 27), (27, 28), (28, 29), (29, 30), (30, 31), (0, 31)]
        mesh = obj.data
        mesh.from_pydata(verts, edges, [])
        mesh.update()

def create_root_widget(rig, bone_name, bone_transform_name=None):
    # From Rigify
    """ Creates a widget for the root bone.
    """
    obj = create_widget(rig, bone_name, bone_transform_name)
    if obj != None:
        verts = [(0.7071067690849304, 0.7071067690849304, 0.0), (0.7071067690849304, -0.7071067690849304, 0.0), (-0.7071067690849304, 0.7071067690849304, 0.0), 
                 (-0.7071067690849304, -0.7071067690849304, 0.0), (0.8314696550369263, 0.5555701851844788, 0.0), (0.8314696550369263, -0.5555701851844788, 0.0), 
                 (-0.8314696550369263, 0.5555701851844788, 0.0), (-0.8314696550369263, -0.5555701851844788, 0.0), (0.9238795042037964, 0.3826834261417389, 0.0), 
                 (0.9238795042037964, -0.3826834261417389, 0.0), (-0.9238795042037964, 0.3826834261417389, 0.0), (-0.9238795042037964, -0.3826834261417389, 0.0), 
                 (0.9807852506637573, 0.19509035348892212, 0.0), (0.9807852506637573, -0.19509035348892212, 0.0), (-0.9807852506637573, 0.19509035348892212, 0.0), 
                 (-0.9807852506637573, -0.19509035348892212, 0.0), (0.19509197771549225, 0.9807849526405334, 0.0), (0.19509197771549225, -0.9807849526405334, 0.0), 
                 (-0.19509197771549225, 0.9807849526405334, 0.0), (-0.19509197771549225, -0.9807849526405334, 0.0), (0.3826850652694702, 0.9238788485527039, 0.0), 
                 (0.3826850652694702, -0.9238788485527039, 0.0), (-0.3826850652694702, 0.9238788485527039, 0.0), (-0.3826850652694702, -0.9238788485527039, 0.0), 
                 (0.5555717945098877, 0.8314685821533203, 0.0), (0.5555717945098877, -0.8314685821533203, 0.0), (-0.5555717945098877, 0.8314685821533203, 0.0), 
                 (-0.5555717945098877, -0.8314685821533203, 0.0), (0.19509197771549225, 1.2807848453521729, 0.0), (0.19509197771549225, -1.2807848453521729, 0.0), 
                 (-0.19509197771549225, 1.2807848453521729, 0.0), (-0.19509197771549225, -1.2807848453521729, 0.0), (1.280785322189331, 0.19509035348892212, 0.0), 
                 (1.280785322189331, -0.19509035348892212, 0.0), (-1.280785322189331, 0.19509035348892212, 0.0), (-1.280785322189331, -0.19509035348892212, 0.0), 
                 (0.3950919806957245, 1.2807848453521729, 0.0), (0.3950919806957245, -1.2807848453521729, 0.0), (-0.3950919806957245, 1.2807848453521729, 0.0), 
                 (-0.3950919806957245, -1.2807848453521729, 0.0), (1.280785322189331, 0.39509034156799316, 0.0), (1.280785322189331, -0.39509034156799316, 0.0), 
                 (-1.280785322189331, 0.39509034156799316, 0.0), (-1.280785322189331, -0.39509034156799316, 0.0), (0.0, 1.5807849168777466, 0.0), 
                 (0.0, -1.5807849168777466, 0.0), (1.5807852745056152, 0.0, 0.0), (-1.5807852745056152, 0.0, 0.0)]
        edges = [(0, 4), (1, 5), (2, 6), (3, 7), (4, 8), (5, 9), (6, 10), (7, 11), (8, 12), (9, 13), (10, 14), (11, 15), (16, 20), (17, 21), (18, 22), (19, 23), (20, 24), 
                 (21, 25), (22, 26), (23, 27), (0, 24), (1, 25), (2, 26), (3, 27), (16, 28), (17, 29), (18, 30), (19, 31), (12, 32), (13, 33), (14, 34), (15, 35), (28, 36), 
                 (29, 37), (30, 38), (31, 39), (32, 40), (33, 41), (34, 42), (35, 43), (36, 44), (37, 45), (38, 44), (39, 45), (40, 46), (41, 46), (42, 47), (43, 47)]
        mesh = obj.data
        mesh.from_pydata(verts, edges, [])
        mesh.update()

def create_sphere_widget(rig, bone_name, bone_transform_name=None):
    """ Creates a basic sphere widget, three pependicular overlapping circles.
    """
    obj = create_widget(rig, bone_name, bone_transform_name)
    if obj != None:
        verts = [(0.3535533845424652, 0.3535533845424652, 0.0), (0.4619397521018982, 0.19134171307086945, 0.0), (0.5, -2.1855694143368964e-08, 0.0), 
                 (0.4619397521018982, -0.19134175777435303, 0.0), (0.3535533845424652, -0.3535533845424652, 0.0), (0.19134174287319183, -0.4619397521018982, 0.0), 
                 (7.549790126404332e-08, -0.5, 0.0), (-0.1913416087627411, -0.46193981170654297, 0.0), (-0.35355329513549805, -0.35355350375175476, 0.0), 
                 (-0.4619397521018982, -0.19134178757667542, 0.0), (-0.5, 5.962440319251527e-09, 0.0), (-0.4619397222995758, 0.1913418024778366, 0.0), 
                 (-0.35355326533317566, 0.35355350375175476, 0.0), (-0.19134148955345154, 0.46193987131118774, 0.0), (3.2584136988589307e-07, 0.5, 0.0), 
                 (0.1913420855998993, 0.46193960309028625, 0.0), (7.450580596923828e-08, 0.46193960309028625, 0.19134199619293213), (5.9254205098113744e-08, 0.5, 2.323586443253589e-07), 
                 (4.470348358154297e-08, 0.46193987131118774, -0.1913415789604187), (2.9802322387695312e-08, 0.35355350375175476, -0.3535533547401428), 
                 (2.9802322387695312e-08, 0.19134178757667542, -0.46193981170654297), (5.960464477539063e-08, -1.1151834122813398e-08, -0.5000000596046448), 
                 (5.960464477539063e-08, -0.1913418024778366, -0.46193984150886536), (5.960464477539063e-08, -0.35355350375175476, -0.3535533845424652), 
                 (7.450580596923828e-08, -0.46193981170654297, -0.19134166836738586), (9.348272556053416e-08, -0.5, 1.624372103492533e-08), 
                 (1.043081283569336e-07, -0.4619397521018982, 0.19134168326854706), (1.1920928955078125e-07, -0.3535533845424652, 0.35355329513549805), 
                 (1.1920928955078125e-07, -0.19134174287319183, 0.46193966269493103), (1.1920928955078125e-07, -4.7414250303745575e-09, 0.49999991059303284), 
                 (1.1920928955078125e-07, 0.19134172797203064, 0.46193966269493103), (8.940696716308594e-08, 0.3535533845424652, 0.35355329513549805), 
                 (0.3535534739494324, 0.0, 0.35355329513549805), (0.1913418173789978, -2.9802322387695312e-08, 0.46193966269493103), 
                 (8.303572940349113e-08, -5.005858838558197e-08, 0.49999991059303284), (-0.19134165346622467, -5.960464477539063e-08, 0.46193966269493103), 
                 (-0.35355329513549805, -8.940696716308594e-08, 0.35355329513549805), (-0.46193963289260864, -5.960464477539063e-08, 0.19134168326854706), 
                 (-0.49999991059303284, -5.960464477539063e-08, 1.624372103492533e-08), (-0.4619397521018982, -2.9802322387695312e-08, -0.19134166836738586), 
                 (-0.3535534143447876, -2.9802322387695312e-08, -0.3535533845424652), (-0.19134171307086945, 0.0, -0.46193984150886536), 
                 (7.662531942287387e-08, 9.546055501630235e-09, -0.5000000596046448), (0.19134187698364258, 5.960464477539063e-08, -0.46193981170654297), 
                 (0.3535535931587219, 5.960464477539063e-08, -0.3535533547401428), (0.4619399905204773, 5.960464477539063e-08, -0.1913415789604187), 
                 (0.5000000596046448, 5.960464477539063e-08, 2.323586443253589e-07), (0.4619396924972534, 2.9802322387695312e-08, 0.19134199619293213)]
        edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8), (8, 9), (9, 10), (10, 11), (11, 12), (12, 13), (13, 14), (14, 15), (0, 15), (16, 31), (16, 17), 
                 (17, 18), (18, 19), (19, 20), (20, 21), (21, 22), (22, 23), (23, 24), (24, 25), (25, 26), (26, 27), (27, 28), (28, 29), (29, 30), (30, 31), (32, 33), (33, 34), 
                 (34, 35), (35, 36), (36, 37), (37, 38), (38, 39), (39, 40), (40, 41), (41, 42), (42, 43), (43, 44), (44, 45), (45, 46), (46, 47), (32, 47)]
        mesh = obj.data
        mesh.from_pydata(verts, edges, [])
        mesh.update()

def create_bone_shapes():
    # Bone Shapes.  Sphere for IK targets, cube for foot/hand/torso
    # Cube for Hand and Foot controllers
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.5, calc_uvs=False)
    me = bpy.data.meshes.new('Mesh')
    bm.to_mesh(me)
    bm.free()
    bone_shape_cube = bpy.data.objects.new('bone_shape_cube', me)
    bone_shape_cube.draw_type = 'WIRE'
    bpy.context.scene.objects.link(bone_shape_cube)
    bone_shape_cube.layers = [False]*19+[True]

    # Sphere for IK Targetes
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=0, diameter=1.0, calc_uvs=False)
    me = bpy.data.meshes.new('Mesh')
    bm.to_mesh(me)
    bm.free()
    bone_shape_sphere = bpy.data.objects.new('bone_shape_sphere', me)
    bone_shape_sphere.draw_type = 'WIRE'
    bpy.context.scene.objects.link(bone_shape_sphere)
    bone_shape_sphere.layers = [False]*19+[True]

    # Single Circle for Root Bone
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=False, diameter=2.0, segments=8)
    me = bpy.data.meshes.new("Mesh")
    bm.to_mesh(me)
    bm.free()
    bone_shape_circle = bpy.data.objects.new("bone_shape_circle", me)
    bpy.context.scene.objects.link(bone_shape_circle)
    bone_shape_circle.layers = [False]*19+[True]

    # Triple Circle for Torso Controllers
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=False, diameter=2.0, segments=8)
    me = bpy.data.meshes.new("Mesh")
    bm.to_mesh(me)
    bm.free()
    bone_shape_torso = bpy.data.objects.new("bone_shape_torso", me)
    bpy.context.scene.objects.link(bone_shape_torso)
    bone_shape_torso.layers = [False]*19+[True]

def create_IKs():
    armature = bpy.data.objects['Armature']
    amt = armature.data
    bpy.context.scene.objects.active = armature
    
    # Get the scaling factor
    #scale = get_scaling_factor(torso)

    bpy.ops.object.mode_set(mode='EDIT')

    # Set up hip and torso bones.
    hip_root_bone = copy_bone(armature, "Bip01_Pelvis", "Hip_Root")
    flip_bone(armature, "Hip_Root")
    # Parent Pelvis to hip_root
    armature.data.edit_bones['Bip01_Pelvis'].parent = armature.data.edit_bones['Hip_Root']
    armature.data.edit_bones['Bip01_Pitch'].use_inherit_rotation = False

    rightThigh = bpy.context.object.data.edit_bones['Bip01_R_Thigh']
    rightCalf = bpy.context.object.data.edit_bones['Bip01_R_Calf']
    leftThigh = bpy.context.object.data.edit_bones['Bip01_L_Thigh']
    leftCalf = bpy.context.object.data.edit_bones['Bip01_L_Calf']
    leftElbow = bpy.context.object.data.edit_bones['Bip01_L_UpperArm']
    leftForearm = bpy.context.object.data.edit_bones['Bip01_L_Forearm']
    rightElbow = bpy.context.object.data.edit_bones['Bip01_R_UpperArm']
    rightForearm = bpy.context.object.data.edit_bones['Bip01_R_Forearm']
    rightHand = bpy.context.object.data.edit_bones['Bip01_R_Hand']
    leftHand = bpy.context.object.data.edit_bones['Bip01_L_Hand'] 
    rightFoot = bpy.context.object.data.edit_bones['Bip01_R_Foot'] 
    leftFoot = bpy.context.object.data.edit_bones['Bip01_L_Foot'] 

    # Determine knee IK offset.  Behind for chickenwalkers, forward for regular.
    if rightCalf.head.y > rightFoot.tail.y:
        offset = 4
    else:
        offset = -4

    ### Create IK bones
    # Right foot
    rightFootIK = amt.edit_bones.new('Foot_IK.R')
    rightFootIK.head = rightCalf.tail
    rightFootIK.tail = rightCalf.tail + mathutils.Vector((0,1,0))
    rightFootIK.use_deform = False

    # Left foot
    leftFootIK = amt.edit_bones.new('Foot_IK.L')
    leftFootIK.head = leftCalf.tail
    leftFootIK.tail = leftCalf.tail + mathutils.Vector((0,1,0))
    leftFootIK.use_deform = False

    # Left knee
    leftKneeIK = amt.edit_bones.new('Knee_IK.L')
    leftKneeIK.head = leftCalf.head + mathutils.Vector((0,offset,0))
    leftKneeIK.tail = leftKneeIK.head + mathutils.Vector((0, offset/4, 0))
    leftKneeIK.use_deform = False
    
    # Right knee
    rightKneeIK = amt.edit_bones.new('Knee_IK.R')
    rightKneeIK.head = rightCalf.head + mathutils.Vector((0,offset,0))
    rightKneeIK.tail = rightKneeIK.head + mathutils.Vector((0, offset/4, 0))
    rightKneeIK.use_deform = False

    # Right Hand
    rightHandIK = amt.edit_bones.new('Hand_IK.R')
    rightHandIK.head = rightHand.head
    rightHandIK.tail = rightHandIK.head + mathutils.Vector((0, 1, 0))
    rightHandIK.use_deform = False

    # Right Elbow
    rightElbowIK = amt.edit_bones.new('Elbow_IK.R')
    rightElbowIK.head = rightForearm.head + mathutils.Vector((0, -4, 0))
    rightElbowIK.tail = rightElbowIK.head + mathutils.Vector((0, -1, 0))
    rightElbowIK.use_deform = False

    # Left Hand
    leftHandIK = amt.edit_bones.new('Hand_IK.L')
    leftHandIK.head = leftHand.head
    leftHandIK.tail = leftHandIK.head + mathutils.Vector((0, 1, 0))
    leftHandIK.use_deform = False

    # Left Elbow
    leftElbowIK = amt.edit_bones.new('Elbow_IK.L')
    leftElbowIK.head = leftForearm.head + mathutils.Vector((0, -4, 0))
    leftElbowIK.tail = leftElbowIK.head + mathutils.Vector((0, -1, 0))
    leftElbowIK.use_deform = False

    # Set custom shapes
    bpy.ops.object.mode_set(mode='OBJECT')
    
    create_root_widget(armature, "Root", "Bip01")
    create_cube_widget(armature, "Hand_IK.R", 1.25, "Hand_IK.R")
    create_cube_widget(armature, "Hand_IK.L", 1.25, "Hand_IK.L")
    create_cube_widget(armature, "Foot_IK.R", 1.0, "Foot_IK.R")
    create_cube_widget(armature, "Foot_IK.L", 1.0, "Foot_IK.L")
    create_sphere_widget(armature, "Knee_IK.R", "Knee_IK.R")
    create_sphere_widget(armature, "Knee_IK.L", "Knee_IK.L")
    create_sphere_widget(armature, "Elbow_IK.R", "Elbow_IK.R")
    create_sphere_widget(armature, "Elbow_IK.L", "Elbow_IK.L")
    create_foot_widget(armature, "Bip01_R_Foot", 1.0, "Bip01_R_Foot")
    create_foot_widget(armature, "Bip01_L_Foot", 1.0, "Bip01_L_Foot")

    bpy.data.objects[WGT_PREFIX + armature.name + "_" + "Root"].rotation_euler = (0,0,0)

    armature.pose.bones['Bip01'].custom_shape = bpy.data.objects[WGT_PREFIX + armature.name + "_" + "Root"]
    armature.pose.bones['Hand_IK.R'].custom_shape = bpy.data.objects[WGT_PREFIX + armature.name + "_" + "Hand_IK.R"]
    armature.pose.bones['Hand_IK.L'].custom_shape = bpy.data.objects[WGT_PREFIX + armature.name + "_" + "Hand_IK.L"]
    armature.pose.bones["Foot_IK.R"].custom_shape = bpy.data.objects[WGT_PREFIX + armature.name + "_" + "Foot_IK.R"]
    armature.pose.bones["Foot_IK.L"].custom_shape = bpy.data.objects[WGT_PREFIX + armature.name + "_" + "Foot_IK.L"]
    armature.pose.bones['Knee_IK.R'].custom_shape = bpy.data.objects[WGT_PREFIX + armature.name + "_" + "Knee_IK.R"]
    armature.pose.bones['Knee_IK.L'].custom_shape = bpy.data.objects[WGT_PREFIX + armature.name + "_" + "Knee_IK.L"]
    armature.pose.bones['Elbow_IK.R'].custom_shape = bpy.data.objects[WGT_PREFIX + armature.name + "_" + "Elbow_IK.R"]
    armature.pose.bones['Elbow_IK.L'].custom_shape = bpy.data.objects[WGT_PREFIX + armature.name + "_" + "Elbow_IK.L"]
    armature.pose.bones['Bip01_L_Foot'].custom_shape = bpy.data.objects[WGT_PREFIX + armature.name + "_" + "Bip01_L_Foot"]
    armature.pose.bones['Bip01_R_Foot'].custom_shape = bpy.data.objects[WGT_PREFIX + armature.name + "_" + "Bip01_R_Foot"]

    # Set up IK Constraints
    bpy.ops.object.mode_set(mode='POSE')
    bpose = bpy.context.object.pose

    # Add copy rotation constraint to pitch
    crc = armature.pose.bones["Bip01_Pitch"].constraints.new('COPY_ROTATION')
    crc.target = armature
    crc.subtarget = "Bip01_Pelvis"
    crc.target_space = 'LOCAL'
    crc.owner_space = 'LOCAL'

    amt.bones['Bip01_L_Foot'].use_inherit_rotation = False
    amt.bones['Bip01_R_Foot'].use_inherit_rotation = False

    bpose.bones['Bip01_R_Hand'].constraints.new(type='IK')
    bpose.bones['Bip01_R_Hand'].constraints['IK'].target = armature
    bpose.bones['Bip01_R_Hand'].constraints['IK'].subtarget = 'Hand_IK.R'
    if "Bip01_R_Elbow" in bpose.bones.keys():
        bpose.bones['Bip01_R_Hand'].constraints['IK'].chain_count = 5
    else:
        bpose.bones['Bip01_R_Hand'].constraints['IK'].chain_count = 3


    bpose.bones['Bip01_L_Hand'].constraints.new(type='IK')
    bpose.bones['Bip01_L_Hand'].constraints['IK'].target = armature
    bpose.bones['Bip01_L_Hand'].constraints['IK'].subtarget = 'Hand_IK.L'
    if "Bip01_L_Elbow" in bpose.bones.keys():
        bpose.bones['Bip01_L_Hand'].constraints['IK'].chain_count = 5
    else:
        bpose.bones['Bip01_L_Hand'].constraints['IK'].chain_count = 3

    bpose.bones['Bip01_R_UpperArm'].constraints.new(type='IK')
    bpose.bones['Bip01_R_UpperArm'].constraints['IK'].target = armature
    bpose.bones['Bip01_R_UpperArm'].constraints['IK'].subtarget = 'Elbow_IK.R'
    bpose.bones['Bip01_R_UpperArm'].constraints['IK'].chain_count = 1

    bpose.bones['Bip01_L_UpperArm'].constraints.new(type='IK')
    bpose.bones['Bip01_L_UpperArm'].constraints['IK'].target = armature
    bpose.bones['Bip01_L_UpperArm'].constraints['IK'].subtarget = 'Elbow_IK.L'
    bpose.bones['Bip01_L_UpperArm'].constraints['IK'].chain_count = 1

    bpose.bones['Bip01_R_Calf'].constraints.new(type='IK')
    bpose.bones['Bip01_R_Calf'].constraints['IK'].target = armature
    bpose.bones['Bip01_R_Calf'].constraints['IK'].subtarget = 'Foot_IK.R'
    bpose.bones['Bip01_R_Calf'].constraints['IK'].chain_count = 2

    bpose.bones['Bip01_L_Calf'].constraints.new(type='IK')
    bpose.bones['Bip01_L_Calf'].constraints['IK'].target = armature
    bpose.bones['Bip01_L_Calf'].constraints['IK'].subtarget = 'Foot_IK.L'
    bpose.bones['Bip01_L_Calf'].constraints['IK'].chain_count = 2
        
    bpose.bones['Bip01_R_Thigh'].constraints.new(type='IK')
    bpose.bones['Bip01_R_Thigh'].constraints['IK'].target = armature
    bpose.bones['Bip01_R_Thigh'].constraints['IK'].subtarget = 'Knee_IK.R'
    bpose.bones['Bip01_R_Thigh'].constraints['IK'].chain_count = 1

    bpose.bones['Bip01_L_Thigh'].constraints.new(type='IK')
    bpose.bones['Bip01_L_Thigh'].constraints['IK'].target = armature
    bpose.bones['Bip01_L_Thigh'].constraints['IK'].subtarget = 'Knee_IK.L'
    bpose.bones['Bip01_L_Thigh'].constraints['IK'].chain_count = 1

    # Turn off inherit rotation for hands
    leftHand.use_inherit_rotation = False
    rightHand.use_inherit_rotation = False
    leftElbowIK.use_inherit_rotation = False
    rightElbowIK.use_inherit_rotation = False

def import_geometry(cdffile, basedir, bodydir, mechname):
    armature = bpy.data.objects['Armature']
    print("Importing mech geometry...")
    geometry = ET.parse(cdffile)
    for geo in geometry.iter("Attachment"):
        if not geo.attrib["AName"] == "cockpit":
            print("Importing " + geo.attrib["AName"])
            # Get all the attribs
            aname    = geo.attrib["AName"]
            rotation = convert_to_rotation(geo.attrib["Rotation"])
            location = convert_to_location(geo.attrib["Position"])
            bonename = geo.attrib["BoneName"].replace(' ','_')
            binding  = os.path.join(basedir, os.path.splitext(geo.attrib["Binding"])[0] + ".dae")
            flags    = geo.attrib["Flags"]
            # Materials depend on the part type.  For most, <mech>_body.  Weapons is <mech>_variant.  Window/cockpit is 
            # <mech>_window.  Also need to figure out how to deal with _generic materials after the import.
            materialname = mechname + "_body"
            if any(weapon in aname for weapon in weapons):
                materialname = mechname + "_variant"
            if "_damaged" in aname or "_prop" in aname:
                materialname = mechname + "_body"
            if "head_cockpit" in aname:
                materialname = mechname + "_window"
            # We now have all the geometry parts that need to be imported, their loc/rot, and material.  Import.
            try:
                bpy.ops.wm.collada_import(filepath=binding,find_chains=True,auto_connect=True)
            except:
                # Unable to open the file.  Probably not found (like Urbie lights, under purchasables).
                continue
            obj_objects = bpy.context.selected_objects[:]
            i = 0
            for obj in obj_objects:
                if not obj.type == 'EMPTY':
                    armature.select = True
                    bpy.context.scene.objects.active = armature
                    bone_location = bpy.context.object.pose.bones[bonename].head
                    bone_rotation = obj.rotation_quaternion
                    #print("    Original loc and rot: " + str(bone_location) + " and " + str(bone_rotation))
                    #print("    Materials for " + obj.name)
                    bpy.context.scene.objects.active = obj
                    print("    Name: " + obj.name)
                    # If this is a parent node, rotate/translate it. Otherwise skip it.
                    if i == 0:
                        matrix = get_transform_matrix(rotation, location)       # Converts the location vector and rotation quat into a 4x4 matrix.
                        #parent this first object to the appropriate bone
                        obj.rotation_mode = 'QUATERNION'
                        bone = armature.data.bones[bonename]
                        obj.parent = armature
                        obj.parent_bone = bonename
                        obj.parent_type = 'BONE'
                        obj.matrix_world = matrix
                        i = i + 1
                    # Vertex groups
                    vg = obj.vertex_groups.new(bonename)
                    nverts = len(obj.data.vertices)
                    for i in range(nverts):
                        vg.add([i], 1.0, 'REPLACE')
                    if len(bpy.context.object.material_slots) == 0:
                        # no materials
                        bpy.context.object.data.materials.append(bpy.data.materials[materialname])               # If there is no material, add a dummy mat.
                    else:
                        # Material corrections.  If material slot 0 contains "generic", it's a generic material, unless the key doesn't exist.  Otherwise stays variant.
                        if "generic" in obj.material_slots[0].name:
                            if  mechname + "_generic" in bpy.data.materials.keys():
                                materialname = mechname + "_generic"
                            else:
                                materialname = "generic"            # For some reason it's just generic, not <mech>_generic
                        else:
                            materialname = mechname + "_variant"
                        if "_prop" in obj.name:
                            materialname = mechname + "_body"
                        bpy.context.object.data.materials[0] = bpy.data.materials[materialname]
                    obj.select = False

def set_viewport_shading():
    # Set material mode. # iterate through areas in current screen
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces: 
                if space.type == 'VIEW_3D': 
                    space.viewport_shade = 'MATERIAL'

def set_layers():
    # Set the layers that objects are on.
    empties = [obj for obj in bpy.data.objects 
               if obj.name.startswith('fire') 
               or 'physics_proxy' in obj.name 
               or obj.name.endswith('_fx') 
               or obj.name.endswith('_case')
               or obj.name.startswith('animation')]
    for empty in empties:
        empty.layers[4] = True
        empty.layers[0] = False
    # Set weapons and special geometry to layer 2
    names = bpy.data.objects.keys()
    for name in names:
        if any(x in name for x in weapons):
            bpy.data.objects[name].layers[1] = True
            bpy.data.objects[name].layers[0] = False

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
    cockpit_matfile = os.path.join(mechdir, "cockpit_standard", mech + 
                                   "_a_cockpit_standard.mtl")

    # Create the bone shapes.  Lots of ops operations, so start it at the 
    # beginning where draw calls aren't as expensive.
    #create_bone_shapes()  # Now using Rigify options

    bpy.context.scene.render.engine = 'CYCLES'      # Set to cycles mode
    
    # Set material mode. # iterate through areas in current screen
    set_viewport_shading()
    
    # Try to import the armature.  If we can't find it, then return error.
    result = import_armature(os.path.join(bodydir, mech + ".dae"))   # import the armature.
    if result == False:    
        print("Error importing armature at: " + 
              os.path.join(bodydir, mech + ".dae"))
        return False

    # Create the materials.
    materials = create_materials(matfile, basedir)
    cockpit_materials = create_materials(cockpit_matfile, basedir)
    # Import the geometry and assign materials.
    geometry = import_geometry(cdffile, basedir, bodydir, mech)

    # Set the layers for existing objects
    set_layers()

    # Advanced Rigging stuff.  Make bone shapes, IKs, etc.
    bpy.ops.object.mode_set(mode='EDIT')
    create_IKs()
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

#IOOBJOrientationHelper = orientation_helper_factory("IOOBJOrientationHelper", axis_forward='-Z', axis_up='Y')
IOOBJOrientationHelper = orientation_helper_factory("IOOBJOrientationHelper", axis_forward='Y', axis_up='Z')

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


