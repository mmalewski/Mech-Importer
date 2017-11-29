# Powershell script to create a text output that can be put in the Blender script engine to import
# all the mech chassis components into the proper position.
# Geoff Gerber, 10/27/2013 (markemp@gmail.com)
# 1/20/2014 - strips material from obj, removes doubles, tris to quads
# 1/25/2014 - Input now reads the xml file instead of using regex to parse the text file.  Should be much more robust
#        Removing the need to input the path; instead just set $basedir in the script.          
# version 1.33 (3/10/14) - Updated to properly assign materials based on material type, instead of guessing by position in array
# version 1.5 (6/12/14) - Modified to work with the new Clan mech files
# version 1.6 (12/30/14) - Fixing bugs with Wave 2 mechs, variant/window materials assigned, general cleanup
# Version 1.61 (8/9/15)  - Bug fixes (Blender 2.73+ crash, atlas_movie.cdf issue)
# Version 2.0 (10/06/17) - Supports Collada files created by the 1.0 version of cgf-converter (https://www.heffaypresents.com/GitHub)
# Version 2.0.1 (11/26/17) - Layer management, bug fixes

# Input is the .cdf file in the mech directory for the mech you want
# output is the text of what you want to put into Blender.  It also outputs to import.txt in the directory you
# run the script from.

param (
    [string]$cdffile,                     # location of the mech's .cdf file.  Usually at Objects\Mechs\<mech>.  If running from a directory other than this, can set it here.
	[string]$objectdir,                   # Where the game .pak files are extracted to.
	[switch]$dae = $true,                 # Defaults to Collada.  If cgf-exporter gets more exporters, there will be more options for this.
	[switch]$obj = $false,
	[string]$imageformat = "dds"          # Default image file format.  If you want to use .pngs, change this (although you probably don't want to.
)

# Python commands used by Blender
$scriptimport = "bpy.ops.import_scene.obj"
$scriptimportCollada = "bpy.ops.wm.collada_import"
$scriptscene = "bpy.context.scene.objects.active"
$scriptrotationmode = "bpy.context.active_object.rotation_mode='QUATERNION'"
$scriptrotation = "bpy.context.active_object.rotation_quaternion"
$scripttransform = "bpy.context.active_object.location"
$scriptremovedoubles = "bpy.ops.mesh.remove_doubles()"
$scripttristoquads = "bpy.ops.mesh.tris_convert_to_quads()"
$scriptseteditmode = "bpy.ops.object.mode_set(mode='EDIT')"
$scriptsetobjectmode = "bpy.ops.object.mode_set(mode='OBJECT')"
$scriptclearmaterial = "bpy.context.object.data.materials.clear(update_data=True)"   #only works with 2.69 or newer. Bug fix 1.61:  added update_data

function Get-Usage {
    Write-host "Usage:  mech-importer <-cdffile <mech .cdf file location>><[-objectdir '<directory to \Object>']> <[-dae|-obj]> <-imageformat [dds]|[tif]>" -ForegroundColor Green
	Write-Host "        Takes a mech's cdf file (in Objects\Mechs\<mech>) and creates an import.txt file that"
	Write-Host "        can be pasted into the Blender python console.  This will import all the mech parts"
	Write-Host "        (assuming they've been converted to .dae or .obj) into Blender and create the appropriate"
	Write-Host "        materials.\n"
	Write-Host
    Write-Host "        If .cdf file isn't specified, Mech Importer checks the current directory."
    Write-Host "        The following variables need to be properly defined:"
    Write-Host "             `$objectdir:  Where you extracted the object.pak files (and skins)"
    Write-Host "             `$imageformat:  What image format you are using (default .dds.  Also supports tif)"
    Write-Host
	Write-Host "         This will only fully work when imported into Blender 2.79 or newer, as it uses the PrincipledBSDF shader."
    pause
    exit
}

# Generic error checking
if ($PSVersionTable.PSVersion.Major -lt 3) {
	Write-Host "Requires at least Powershell version 3.  This computer is currently using version $PSVersionTable.PSVersion.Major" -ForegroundColor Yellow
	exit 1
}
#

# Argument processing and cleanup
# $type determines if you're using Collada or Waveform files.  Defaults to Collada.
$type = "Collada"
if (!$dae -and $obj) {
	$type = "Waveform"
} 

if (!$objectdir) {
	$basedir = "d:\blender projects\mechs\"    # this is where you extracted all the *.pak files from the game. \objects, \textures etc.  This is my settings
	Write-Host "No -objectdir specified.  Will default to $basedir.  THIS IS PROBABLY NOT WHAT YOU WANT." -ForegroundColor Yellow
} 
else {
	$basedir = $objectdir
	if (!$basedir.EndsWith('\')) {
		$basedir += '\'
	}
}

# convert the path so it can be used by Blender
$basedir = $basedir.replace("\","\\")

# Delete import.txt if it already exists.
try {
	$importtxt = Get-ChildItem "import.txt" -ErrorAction SilentlyContinue
	Remove-Item $importtxt
}
catch  {
	# File not found.
	Write-Host "No existing import.txt file found. (this is ok)"
}

if ($imageformat -eq "tif" -or $imageformat -eq ".tif") {
	$imageformat = ".tif"                   
}
else {
	$imageformat = ".dds"
}

# Set the weapons variable to assign variant materials.  Hero, invasion, blanks and Phoenix parts are variants.
$weapons = "hero","missile","narc","uac", "uac2", "uac5", "uac10", "uac20", "ac2","ac5","ac10","ac20","gauss","ppc","flamer","_mg_","lbx","laser","ams","phoenix","blank","invasion"

#Find the <mech>.cdf file.  If it's not supplied as the argument, check the current directory.
if (!$cdffile) {
	# no cdf file specified.  Check the local directory.
	if (get-childitem *.cdf) {
		#$cdffilelocation = Get-childitem *.cdf   # Doesn't work if there is more than one .cdf file (looking at you Atlas)
		foreach ($file in (Get-ChildItem *.cdf)) {
			if (!$file.Name.Contains("movie")) {
				$cdffilelocation = $file;
			}
		}
	} 
	else {            # unable to find a cdf file in current directory.
		Write-Host "Unable to find a cdf file in current directory, and no -cdffile specified." -ForegroundColor Red
		Get-Usage
		exit
	}
} 
else { # cdffile passed.  Check to see if the file exists.
	if ( !(test-path $cdffile -ErrorAction SilentlyContinue)) {
		write-host "Unable to find .cdf file: $cdffile" -ForegroundColor Red
		exit
	}
	else {
		$cdffilelocation = $cdffile
	}
}

"# Mech Importer 2.0
# https://www.heffaypresents.com/GitHub

import bpy
import bmesh
import math
import mathutils
" >> .\import.txt

# Set Blender to Cycles
"bpy.context.scene.render.engine = 'CYCLES'" >> .\import.txt

# Get mech name from .cdf directory name
$mech = $cdffilelocation.directory.Name
#$mech = $args[0].ToString().Substring(0,($args[0].tostring().Length-4))
if ($mech.startswith(".\")) {   # Need to strip off the .\
    $mech = $mech.replace(".\","")
}
write-host "Mech is $mech"

[xml]$cdffile = get-content $cdffilelocation

# Get $modeldir from XML file.  Path to everything will be $basedir\$modeldir
$modeldir = "\\objects\\mechs\\$mech"

Write-Host "Modeldir is $modeldir"

# *** MATERIALS ***
# Load up materials from the <mech_body.mtl> file
# Assumptions:  The .cdf file we read has the name of the mech in it, and the mtl file is <mech>_body.mtl under the body subdirectory.
[xml]$matfile = get-content ("$basedir\$modeldir\body\$mech" + "_body.mtl")

# If this is a Collada file, add the Armature
if ($type -eq "Collada") {
	$armature = $basedir + $modeldir + "\\body\\" + $mech  + ".dae"
	Write-Host $armature
	$scriptimportCollada + "(filepath=`"$armature`",find_chains=True,auto_connect=True)" >> .\import.txt
}

# Get the 4 materials from $matfile and create them in Blender
#  material append wants an object of type material, not a string.  Will have to generate that.
$matfile.Material.SubMaterials.Material | % {
    $matname = $_.Name   # $matname is the name of the material
    Write-host "Found Material $matname" -ForegroundColor Green

    "$matname=bpy.data.materials.new('$matname')"  >> .\import.txt
    "$matname.use_nodes=True" >> .\import.txt
    "$matname.active_node_material" >> .\import.txt
    "TreeNodes = $matname.node_tree" >> .\import.txt
    "links = TreeNodes.links" >> .\import.txt

"for n in TreeNodes.nodes:
   TreeNodes.nodes.remove(n)
" >> .\import.txt
	
	# Every material will have a PrincipleBSDF and Material output.  Add, place and link those
"shaderPrincipledBSDF = TreeNodes.nodes.new('ShaderNodeBsdfPrincipled')
shaderPrincipledBSDF.location =  300,500
shout=TreeNodes.nodes.new('ShaderNodeOutputMaterial')
shout.location = 500,500
links.new(shaderPrincipledBSDF.outputs[0], shout.inputs[0])
" >> .\import.txt

    $_.textures.Texture | % {
        if ( $_.Map -eq "Diffuse") {
			#Diffuse Material
            $matdiffuse = $_.file.replace(".tif","$imageformat").replace(".dds","$imageformat").replace("/","\\")  #assumes diffuse is in slot 0
"matDiffuse = bpy.data.images.load(filepath=`"$basedir\\$matdiffuse`", check_existing=True)
shaderDiffImg=TreeNodes.nodes.new('ShaderNodeTexImage')
shaderDiffImg.image=matDiffuse
shaderDiffImg.location = 0,600
links.new(shaderDiffImg.outputs[0], shaderPrincipledBSDF.inputs[0])
#links.new(shaderDiffImg.outputs[1], shaderPrincipledBSDF.inputs[15])         # Not quite right.
" >> .\import.txt
            }
                        
        if ($_.Map -eq "Specular") {
			# Specular
            $matspec =  $_.file.replace(".tif","$imageformat").replace(".dds","$imageformat").replace("/","\\") 
"matSpec=bpy.data.images.load(filepath='$basedir\\$matspec', check_existing=True)
shaderSpecImg=TreeNodes.nodes.new('ShaderNodeTexImage')
shaderSpecImg.color_space = 'NONE'
shaderSpecImg.image=matSpec
shaderSpecImg.location = 0,325
links.new(shaderSpecImg.outputs[0], shaderPrincipledBSDF.inputs[5])
" >> .\import.txt
            }   
                    
        if ($_.Map -eq "Bumpmap") {
			# Normal
            $matnormal =  $_.file.replace(".tif","$imageformat").replace(".dds","$imageformat").replace("/","\\") 
"matNormal=bpy.data.images.load(filepath=`"$basedir\\$matnormal`", check_existing=True)
shaderNormalImg=TreeNodes.nodes.new('ShaderNodeTexImage')
shaderNormalImg.color_space = 'NONE'
shaderNormalImg.image=matNormal
shaderNormalImg.location = -100,0
converterNormalMap=TreeNodes.nodes.new('ShaderNodeNormalMap')
converterNormalMap.location = 100,0
links.new(shaderNormalImg.outputs[0], converterNormalMap.inputs[1])
links.new(converterNormalMap.outputs[0], shaderPrincipledBSDF.inputs[17])

### END Material:  $matname

" >> .\import.txt
			}

			# If you need Camo patterns, use the MWO_CAMO3 blend file and replace the materials with it.
#		if ($_.Map -eq "SubSurface") {
#			# Camo pattern.  Will need to split the 3 color channels and then recombine.
#			$matCamo =   $_.file.replace(".tif","$imageformat").replace(".dds","$imageformat").replace("/","\\") 
#"
#matCamo=bpy.data.images.load(filepath='$basedir\\$matCamo', check_existing=True)
#shaderCamoImg=TreeNodes.nodes.new('ShaderNodeTexImage')
#shaderCamoImg.location=-700, 400
#shaderCamoImg.image=matCamo
#rgbSplitter=TreeNodes.nodes.new('ShaderNodeSeparateRGB')
#rgbSplitter.location = -525,400
#link.new(shaderCamoImg.outputs[0], rgbSplitter.inputs[0])
#red=TreeNodes.nodes.new('')
#blue=TreeNodes.nodes.new('')
#green=TreeNodes.nodes.new('')

#"
#>> .\import.txt
#			}
    }
	# Get each material into a material object.

}

#  *** PARSING Files ***
#  Start parsing out $mechline
$cdffile.CharacterDefinition.attachmentlist.Attachment | % {
	# TODO: skip .cdf file  This is the cockpit, which needs to be done with asset importer.

	$aname = $_.AName
	$rotation = $_.Rotation
	$position = $_.Position
	$bonename = $_.BoneName.replace(" ","_")
	$binding = $_.Binding
	
	if ($type -eq "Waveform") {
		$binding = $binding.replace(".cga",".obj")
		$binding = $binding.replace(".cgf",".obj")
	} else {
		$binding = $binding.replace(".cga",".dae")
		$binding = $binding.replace(".cgf",".dae")
	}
	$binding_modified = $binding.replace("\","\\").replace("/","\\")  # For use by script.  bug-fix for v1.6
	#$binding_modified = $binding.replace("/","\\")  # For use by script
	# Bug here.  If $binding_modified has just a regular \ as part of the path, Blender python console doesn't
	# read it properly.  Replaces it with x08.  Need to replace single \ with \\.
	$flags = $_.Flags

	# Figure out how to get the object name from $binding.
	$objectname = $binding.split("/").split("\\")
	$objectname = $objectname[-1]  #grabs last part of path
	$objectname = $objectname.substring(0,$objectname.length-4) #strip last 4 characters 

	# Assign the material based on the $objectname.  If it contains something in $weapon, assign the variant.
	# Technically this is overly complex, as the cdf file doesn't accurately identify the material.  <mech>_body
	# is assigned to basically everything even if it's a variant.
	if ($_.material) {  # Material doesn't exist for every object.  Don't set it if it doesn't.
		$material = $_.Material
		$matname = $material.split("/").split("\")  # v1.6 bugfix:  Adds split("\") so it'll split off either way.
		$matname = $matname[-1]
		foreach ($weapon in $weapons) {
			if ($aname.contains($weapon)) {  # We have a variant material
				$matname = $mech+"_variant"
				#write-host "variant found.  applying material $matname" -ForegroundColor Yellow
			}
		}
		if ($objectname.EndsWith("head_cockpit")) { # Apply the window material
			$matname = $mech+"_window"
			#write-host "Window found.  Applying $matname" -ForegroundColor Red
		}
       
		$material = $material.replace("\","\\").replace("/","\\")  # v1.6 bugfix:  Adds replace("\","\\") so materials get assigned properly
	}

	# Time to generate the commands (in $parsedline, an array)
	$parsedline = @()
	# if it's a cockpit item, it'll have multiple groups.  to avoid screwing up naming, we will import these keeping the vertex
	# order with split_mode('OFF').  We do NOT want to remove doubles though, as this destroys the UVMap.
	if ( $objectname.Contains("cockpit")) {
		if ($type -eq "Waveform") {
			$parsedline += $scriptimport + "(filepath=`"$basedir\\$binding_modified`",use_groups_as_vgroups=True,split_mode=`'OFF`')" 
		} 
		else {
			$parsedline += $scriptimportCollada + "(filepath=`"$basedir\\$binding_modified`",find_chains=True,auto_connect=True)" 
		}
	}
	else {
		if ($type -eq "Waveform") {
			$parsedline += $scriptimport + "(filepath=`"$basedir\\$binding_modified`",use_groups_as_vgroups=True,split_mode=`'OFF`')" 
		} 
		else {
			$parsedline += $scriptimportCollada + "(filepath=`"$basedir\\$binding_modified`",find_chains=True,auto_connect=True)" 
		}
	}
    
	# set new object as the active object
	$parsedline += $scriptscene + "=bpy.data.objects[`"$objectname`"]"
	$parsedline += "bpy.ops.object.parent_set(type='OBJECT')"                 # If there are any proxies or hardpoints, this will parent them to geometry.
	# Parent the object to the Armature:  Assumes armature name is Armature and that it's been imported!
	# $parsedline += $scriptscene + "=bpy.data.objects[`"Armature`"]"
	# We may at this point (someday) to replace $objectname (above) with the $Aname, but for now let's stick with $objectname
	# Only rotate/transform an item if it's not a proxy or begins with $.
	if (!$objectname.Contains("proxy") -and !$objectname.StartsWith("$" )) {
		$parsedline += $scriptrotationmode 
		$parsedline += $scriptrotation + "=[$rotation]"
		#$parsedline += $scripttransform + "(value=($position))"
		$parsedline += $scripttransform + " =[$position]"
		# $parsedline += $scripttristoquads
		# Create a vertex group with the bone name.  This makes parenting to armature super easy!
		$parsedline += $scriptseteditmode
		$parsedline += "bpy.ops.object.vertex_group_add()"
		$parsedline += "bpy.context.object.vertex_groups.active.name = `"$bonename`""
		$parsedline += "bpy.ops.mesh.select_all(action=`'SELECT`')"
		$parsedline += "bpy.ops.object.vertex_group_assign()"
		$parsedline += "bpy.ops.mesh.select_all(action=`'TOGGLE`')"

		$parsedline += $scriptsetobjectmode
		#$parsedline += $scriptclearmaterial                     # Not sure if I want to do this or not.  Might wipe the BI materials from the .mtl file.
		$parsedline += "bpy.context.object.data.materials.append($matname)"
	}

	foreach ( $line in $parsedline ) {
		$line >> .\import.txt
	}
}

if ($type -eq "Collada") {
	# Parent all the objects to the armature except empties. If you select an empty, it will start following the root and not its original parent.
	#"bpy.ops.object.select_all(action='SELECT')
"objects = bpy.data.objects
for obj in objects:
    if obj.type != 'EMPTY' and obj.name != 'Lamp' and obj.name != 'Camera' and obj.name != 'Cube':
        obj.select = True

selected_objects = bpy.context.selected_objects
armature = bpy.data.objects['Armature']
amt=armature.data
armature.show_x_ray = True
armature.data.show_axes = True
armature.data.draw_type = 'BBONE'
selected_objects.remove(armature)
bpy.context.scene.objects.active = armature
bpy.ops.object.parent_set(type='ARMATURE_NAME', xmirror=False, keep_transform=True)
" >> .\import.txt
}

# Create IK Bones.  Need to identify all the bones that will have IKs applied to.
# Create the custom shapes on layer 11.  Place the bones using the custom shapes, 
# then 
"bpy.ops.object.mode_set(mode='EDIT')

# Bone Shapes.  Sphere for IK targets, cube for foot/hand/torso
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.5, calc_uvs=False)
me = bpy.data.meshes.new('Mesh')
bm.to_mesh(me)
bm.free()
bone_shape_cube = bpy.data.objects.new('bone_shape_cube', me)
bone_shape_cube.draw_type = 'WIRE'
bpy.context.scene.objects.link(bone_shape_cube)
bone_shape_cube.layers = [False]*19+[True]

bm = bmesh.new()
bmesh.ops.create_icosphere(bm, subdivisions=0, diameter=1.0, calc_uvs=False)
me = bpy.data.meshes.new('Mesh')
bm.to_mesh(me)
bm.free()
bone_shape_sphere = bpy.data.objects.new('bone_shape_sphere', me)
bone_shape_sphere.draw_type = 'WIRE'
bpy.context.scene.objects.link(bone_shape_sphere)
bone_shape_sphere.layers = [False]*19+[True]

bpy.ops.object.mode_set(mode='EDIT')
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

### Create IK bones
# Right foot
rightFootIK = amt.edit_bones.new('Foot_IK.R')
rightFootIK.head = rightCalf.tail
rightFootIK.tail = rightCalf.tail + Vector((0,1,0))
rightFootIK.use_deform = False

# Right knee
rightKneeIK = amt.edit_bones.new('Knee_IK.R')
rightKneeIK.head = rightCalf.head + Vector((0,-4,0))
rightKneeIK.tail = rightKneeIK.head + Vector ((0,-1,0))
rightKneeIK.use_deform = False

# Left foot
leftFootIK = amt.edit_bones.new('Foot_IK.L')
leftFootIK.head = leftCalf.tail
leftFootIK.tail = leftCalf.tail + Vector((0,1,0))
leftFootIK.use_deform = False

# Left knee
leftKneeIK = amt.edit_bones.new('Knee_IK.L')
leftKneeIK.head = leftCalf.head + Vector((0,-4,0))
leftKneeIK.tail = leftKneeIK.head + Vector((0,-1,0))
leftKneeIK.use_deform = False

# Right Hand
rightHandIK = amt.edit_bones.new('Hand_IK.R')
rightHandIK.head = rightHand.head
rightHandIK.tail = rightHandIK.head + Vector((0, 1, 1))
rightHandIK.use_deform = False

# Right Elbow
rightElbowIK = amt.edit_bones.new('Elbow_IK.R')
rightElbowIK.head = rightForearm.head + Vector((0, -4, 0))
rightElbowIK.tail = rightElbowIK.head + Vector((0, -1, 0))
rightElbowIK.use_deform = False

# Left Hand
leftHandIK = amt.edit_bones.new('Hand_IK.L')
leftHandIK.head = leftHand.head
leftHandIK.tail = leftHandIK.head + Vector((0, 1, 1))
leftHandIK.use_deform = False

# Left Elbow
leftElbowIK = amt.edit_bones.new('Elbow_IK.L')
leftElbowIK.head = leftForearm.head + Vector((0, -4, 0))
leftElbowIK.tail = leftElbowIK.head + Vector((0, -1, 0))
leftElbowIK.use_deform = False

# Set custom shapes
bpy.ops.object.mode_set(mode='OBJECT')
armature.pose.bones['Foot_IK.R'].custom_shape = bone_shape_cube
bpy.context.object.data.bones['Foot_IK.R'].show_wire = True
armature.pose.bones['Foot_IK.L'].custom_shape = bone_shape_cube
bpy.context.object.data.bones['Foot_IK.L'].show_wire = True
armature.pose.bones['Knee_IK.R'].custom_shape = bone_shape_sphere
bpy.context.object.data.bones['Knee_IK.R'].show_wire = True
armature.pose.bones['Knee_IK.L'].custom_shape = bone_shape_sphere
bpy.context.object.data.bones['Knee_IK.L'].show_wire = True
armature.pose.bones['Hand_IK.R'].custom_shape = bone_shape_cube
bpy.context.object.data.bones['Hand_IK.R'].show_wire = True
armature.pose.bones['Hand_IK.L'].custom_shape = bone_shape_cube
bpy.context.object.data.bones['Hand_IK.L'].show_wire = True
armature.pose.bones['Elbow_IK.R'].custom_shape = bone_shape_sphere
bpy.context.object.data.bones['Elbow_IK.R'].show_wire = True
armature.pose.bones['Elbow_IK.L'].custom_shape = bone_shape_sphere
bpy.context.object.data.bones['Elbow_IK.L'].show_wire = True

# Set up IK Constraints
bpy.ops.object.mode_set(mode='POSE')
bpose = bpy.context.object.pose

bpose.bones['Bip01_R_Forearm'].constraints.new(type='IK')
bpose.bones['Bip01_R_Forearm'].constraints['IK'].target = bpy.data.objects['Armature']
bpose.bones['Bip01_R_Forearm'].constraints['IK'].subtarget = 'Hand_IK.R'
bpose.bones['Bip01_R_Forearm'].constraints['IK'].chain_count = 2

bpose.bones['Bip01_L_Forearm'].constraints.new(type='IK')
bpose.bones['Bip01_L_Forearm'].constraints['IK'].target = bpy.data.objects['Armature']
bpose.bones['Bip01_L_Forearm'].constraints['IK'].subtarget = 'Hand_IK.L'
bpose.bones['Bip01_L_Forearm'].constraints['IK'].chain_count = 2

bpose.bones['Bip01_R_UpperArm'].constraints.new(type='IK')
bpose.bones['Bip01_R_UpperArm'].constraints['IK'].target = bpy.data.objects['Armature']
bpose.bones['Bip01_R_UpperArm'].constraints['IK'].subtarget = 'Elbow_IK.R'
bpose.bones['Bip01_R_UpperArm'].constraints['IK'].chain_count = 1

bpose.bones['Bip01_L_UpperArm'].constraints.new(type='IK')
bpose.bones['Bip01_L_UpperArm'].constraints['IK'].target = bpy.data.objects['Armature']
bpose.bones['Bip01_L_UpperArm'].constraints['IK'].subtarget = 'Elbow_IK.L'
bpose.bones['Bip01_L_UpperArm'].constraints['IK'].chain_count = 1


" >> .\import.txt

# Set material mode. # iterate through areas in current screen
"for area in bpy.context.screen.areas:
	if area.type == 'VIEW_3D':
		for space in area.spaces: 
			if space.type == 'VIEW_3D': 
				space.viewport_shade = 'MATERIAL'
				" >> .\import.txt

# Move all the empties to layer 5
"empties = [obj for obj in bpy.data.objects if obj.name.startswith('fire') or obj.name.startswith('`$physics') or obj.name.endswith('_fx') or obj.name.endswith('_case')]
for empty in empties:
	empty.layers[4] = True
	empty.layers[0] = False

" >> .\import.txt

# Move all the weapons/custom geometry to layer 2
foreach ($weapon in $weapons) {
	#"weapon = [obj for obj in bpy.data.objects if obj.name."
}

# Create a Group for the mech to make Linking in other blend files simpler.
#"Generate Groups for each object." >> .\import.txt
#"for obj in bpy.context.selectable_objects:
#	if (obj.name != 'Camera' and obj.name != 'Lamp' and obj.name != 'Cube'):
#		bpy.data.groups.new(obj.name)
#		bpy.data.groups[obj.name].objects.link(obj)
#" >> .\import.txt

"" >> .\import.txt # Send a final line feed.


