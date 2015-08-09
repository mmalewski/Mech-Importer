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

# Input is the .cdf file in the mech directory for the mech you want
# output is the text of what you want to put into Blender.  It also outputs to import.txt in the directory you
# run the script from.

# Input:  the directory to all the .obj files put in.

function Get-Usage {
    Write-host "Usage:  mech-importer <mech .cdf file>" -ForegroundColor Yellow
    Write-Host "        If .cdf file isn't specified, Mech Importer checks the current directory"
    Write-Host "        Please update the script before running.  The following variables need to be properly defined:"
    Write-Host "             `$basedir:  Where you extracted the object.pak files (and skins)"
    Write-Host "             `$imageformat:  What image format you are using (default .dds)"
    Write-Host ""
    Write-Host "        Please use Noesis with the cryengine plug-in to convert all the .cgf files to .obj with -flipUV first"
    Write-Host "        See https://www.youtube.com/playlist?list=PL106ZeLhxxVn551_IKGKeU_LBODtkh29b for tutorials."
    Write-Host
    pause
    exit
}

$basedir = "e:\blender projects\mechs"  # this is where you extracted all the *.pak files from the game. \objects, \textures etc
                                        # will be under this dir
$imageformat = ".dds"                   # Default image file format.  If you want to use .pngs, change this

# convert the path so it can be used by Blender
$basedir = $basedir.replace("\","\\")

# Set the weapons variable to assign variant materials.  Hero, invasion, blanks and Phoenix parts are variants.
$weapons = "hero","missile","narc","uac","ac2","ac5","ac10","ac20","gauss","ppc","flamer","_mg_","lbx","laser","ams","phoenix","blank","invasion"

# Python commands used by Blender
$scriptimport = "bpy.ops.import_scene.obj"
$scriptscene = "bpy.context.scene.objects.active"
$scriptrotationmode = "bpy.context.active_object.rotation_mode=`"QUATERNION`""
$scriptrotation = "bpy.context.active_object.rotation_quaternion"
$scripttransform = "bpy.ops.transform.translate"
$scriptremovedoubles = "bpy.ops.mesh.remove_doubles()"
$scripttristoquads = "bpy.ops.mesh.tris_convert_to_quads()"
$scriptseteditmode = "bpy.ops.object.mode_set(mode = `"EDIT`")"
$scriptsetobjectmode = "bpy.ops.object.mode_set(mode = `"OBJECT`")"
#$scriptclearmaterial = "bpy.context.object.data.materials.pop(0, update_data=True)"
$scriptclearmaterial = "bpy.context.object.data.materials.clear(update_data=True)"   #only works with 2.69 or newer. Bug fix 1.61:  added update_data

# if no argument is found, try to find the cdf file in the current directory.
$directory = (Get-ChildItem).directory[0].name  # $directory should have the name of the mech
write-host "Directory set to $directory"

#Find the mech.cdf file.  If it's not supplied as the argument, check the current directory.
if ( $args[0] ) {  # argument passed.  See if it's the cdf file.
    if ( (test-path $args[0]) -and ($args[0].contains("cdf"))) {
        $cdffilelocation = get-childitem $args[0]
    } else {
        Get-Usage
        exit
    }
} # no args entered.  Check current directory.
if ( (get-childitem *.cdf)) {
    #$cdffilelocation = Get-childitem *.cdf   # Doesn't work if there is more than one .cdf file (looking at you Atlas)
	foreach ($file in (Get-ChildItem *.cdf)) {
		if (!$file.Name.Contains("movie")) {
			$cdffilelocation = this;
		}
	}
} else {
    write-host "Unable to find .cdf file." -ForegroundColor Red
    Get-Usage
    exit
}

if ( !(test-path $cdffilelocation)) {
	write-host "Unable to find .cdf file" -ForegroundColor Red
	exit
}

# Get mech name from .cdf file name
$mech = $cdffilelocation.directory.Name
#$mech = $args[0].ToString().Substring(0,($args[0].tostring().Length-4))
if ($mech.startswith(".\")) {   # Need to strip off the .\
    $mech = $mech.replace(".\","")
}
write-host "Mech is $mech"

#function parent_bone parents $object to $bone  TBD
function parent_bone($object, $bone) {
}

[xml]$cdffile = get-content $cdffilelocation



# Get $modeldir from XML file.  Path to everything will be $basedir\$modeldir
#$modeldir = $cdffile.Characterdefinition.Model.Material
#$modeldir = $modeldir.replace("/","\\")
#$modeldir = $modeldir.Trimend("$mech")
# Above logic doesn't work, because .cdf file isn't consistent among models.  However, modeldir is always objects\mechs\<mechname>
$modeldir = "\\objects\\mechs\\$mech"

Write-Host "Modeldir is $modeldir"

# *** MATERIALS ***
# Load up materials from the <mech_body.mtl> file
# Assumptions:  The .cdf file we read has the name of the mech in it, and the mtl file is <mech>_body.mtl under the body subdirectory.
#               For the cockpit, the mtl file is <mech>_a_cockpit_standard, and under the cockpit_standard subdir.
[xml]$matfile = get-content ("$basedir\$modeldir\body\$mech" + "_body.mtl")
[xml]$matcockpitfile = Get-Content ("$basedir\$modeldir\cockpit_standard\$mech" + "_a_cockpit_standard.mtl")

# Set Blender to Cycles
"bpy.context.scene.render.engine = 'CYCLES'" >> .\import.txt

# Get the 4 materials from $matfile and create them in Blender
#  material append wants an object of type material, not a string.  Will have to generate that.
# Since we can't really generate a node layout at this time, we're just going to open the image files
# so it's easier for the user to generate.
$matfile.Material.SubMaterials.Material | % {
    $matname = $_.Name   # $matname is the name of the material
    "$matname=bpy.data.materials.new('$matname')"  >> .\import.txt
    "$matname.use_nodes=True" >> .\import.txt
    #"bpy.context.object.active_material_index = 0" >> .\import.txt
    "$matname.active_node_material" >> .\import.txt
    "TreeNodes = $matname.node_tree" >> .\import.txt
    "links = TreeNodes.links" >> .\import.txt

    "for n in TreeNodes.nodes:" >> .\import.txt
    "    TreeNodes.nodes.remove(n)" >> .\import.txt
    "" >> .\import.txt

    Write-host "Found Material $matname" -ForegroundColor Green
    $_.textures.Texture | % {
        if ( $_.Map -eq "Diffuse") {
            $matdiffuse = $_.file.replace(".tif","$imageformat").replace(".dds","$imageformat").replace("/","\\")  #assumes diffuse is in slot 0
            "matDiffuse = bpy.data.images.load(filepath=`"$basedir\\$matdiffuse`")" >> .\import.txt
            "shaderDiffuse=TreeNodes.nodes.new('ShaderNodeBsdfDiffuse')" >> .\import.txt
            "shaderMix=TreeNodes.nodes.new('ShaderNodeMixShader')" >> .\import.txt
            "shout=TreeNodes.nodes.new('ShaderNodeOutputMaterial')" >> .\import.txt
            "shaderDiffImg=TreeNodes.nodes.new('ShaderNodeTexImage')" >> .\import.txt
            "shaderDiffImg.image=matDiffuse" >> .\import.txt
            "shaderDiffuse.location = 100,500" >> .\import.txt
            "shout.location = 500,400" >> .\import.txt
            "shaderMix.location = 300,500" >> .\import.txt
            "shaderDiffImg.location = -100,500" >> .\import.txt
            "links.new(shaderDiffuse.outputs[0],shaderMix.inputs[1])" >> .\import.txt
            "links.new(shaderMix.outputs[0],shout.inputs[0])" >> .\import.txt
            "links.new(shaderDiffImg.outputs[0],shaderDiffuse.inputs[0])" >> .\import.txt
            }
                        
        if ($_.Map -eq "Specular") {
            $matspec =  $_.file.replace(".tif","$imageformat").replace(".dds","$imageformat").replace("/","\\") 
            "matSpec=bpy.data.images.load(filepath=`"$basedir\\$matspec`")" >> .\import.txt
            "shaderSpec=TreeNodes.nodes.new('ShaderNodeBsdfGlossy')" >> .\import.txt
            "shaderSpecImg=TreeNodes.nodes.new('ShaderNodeTexImage')" >> .\import.txt
            "shaderSpecImg.image=matSpec" >> .\import.txt
            "shaderSpec.location = 100,300" >> .\import.txt
            "shaderSpecImg.location = -100,300" >> .\import.txt
            "links.new(shaderSpec.outputs[0],shaderMix.inputs[2])" >> .\import.txt
            "links.new(shaderSpecImg.outputs[0],shaderSpec.inputs[0])" >> .\import.txt
            }   
                    
        if ($_.Map -eq "Bumpmap") {
            $matnormal =  $_.file.replace(".tif","$imageformat").replace(".dds","$imageformat").replace("/","\\") 
            "matNormal=bpy.data.images.load(filepath=`"$basedir\\$matnormal`")" >> .\import.txt
            "shaderNormalImg=TreeNodes.nodes.new('ShaderNodeTexImage')" >> .\import.txt
            "shaderRGBtoBW=TreeNodes.nodes.new('ShaderNodeRGBToBW')" >> .\import.txt
            "shaderNormalImg.image=matNormal" >> .\import.txt
            "shaderNormalImg.location = -100,100" >> .\import.txt
            "shaderRGBtoBW.location = 100,100" >> .\import.txt
            "links.new(shaderNormalImg.outputs[0],shaderRGBtoBW.inputs[0])" >> .\import.txt
            "links.new(shaderRGBtoBW.outputs[0],shout.inputs[2])" >> .\import.txt
        }
    }
    #$cTex = "bpy.data.materials.new('$matname')"
    #$cTeximage = $matdiffuse

}

$matcockpitfile.Material.SubMaterials.Material | % {
    $matname = $_.Name
    "$matname=bpy.data.materials.new('$matname')"  >> .\import.txt
    "$matname.use_nodes=True" >> .\import.txt
    "$matname.active_node_material" >> .\import.txt
    "TreeNodes = $matname.node_tree" >> .\import.txt
    "links = TreeNodes.links" >> .\import.txt

    "for n in TreeNodes.nodes:" >> .\import.txt
    "    TreeNodes.nodes.remove(n)" >> .\import.txt
    "" >> .\import.txt
    $_.textures.Texture | % {
        if ( $_.Map -eq "Diffuse") {
            $matdiffuse = $_.file.replace(".tif","$imageformat").replace(".dds","$imageformat").replace("/","\\")  #assumes diffuse is in slot 0
            if ( $matdiffuse.contains("@") ) {  #fixes monitor materials where it assigns a file that doesn't exist
                $matdiffuse = "$basedir\\libs\\UI\\HUD\\Screens\\Monitors\\killcount_i7.png"
            }
            "matDiffuse = bpy.data.images.load(filepath=`"$basedir\\$matdiffuse`")" >> .\import.txt
            "shaderDiffuse=TreeNodes.nodes.new('ShaderNodeBsdfDiffuse')" >> .\import.txt
            "shaderMix=TreeNodes.nodes.new('ShaderNodeMixShader')" >> .\import.txt
            "shout=TreeNodes.nodes.new('ShaderNodeOutputMaterial')" >> .\import.txt
            "shaderDiffImg=TreeNodes.nodes.new('ShaderNodeTexImage')" >> .\import.txt
            "shaderDiffImg.image=matDiffuse" >> .\import.txt
            "shaderDiffuse.location = 100,500" >> .\import.txt
            "shout.location = 500,400" >> .\import.txt
            "shaderMix.location = 300,500" >> .\import.txt
            "shaderDiffImg.location = -100,500" >> .\import.txt
            "links.new(shaderDiffuse.outputs[0],shaderMix.inputs[1])" >> .\import.txt
            "links.new(shaderMix.outputs[0],shout.inputs[0])" >> .\import.txt
            "links.new(shaderDiffImg.outputs[0],shaderDiffuse.inputs[0])" >> .\import.txt
            }
                        
        if ($_.Map -eq "Specular") {
            $matspec =  $_.file.replace(".tif","$imageformat").replace(".dds","$imageformat").replace("/","\\") 
            "matSpec=bpy.data.images.load(filepath=`"$basedir\\$matspec`")" >> .\import.txt
            "shaderSpec=TreeNodes.nodes.new('ShaderNodeBsdfGlossy')" >> .\import.txt
            "shaderSpecImg=TreeNodes.nodes.new('ShaderNodeTexImage')" >> .\import.txt
            "shaderSpecImg.image=matSpec" >> .\import.txt
            "shaderSpec.location = 100,300" >> .\import.txt
            "shaderSpecImg.location = -100,300" >> .\import.txt
            "links.new(shaderSpec.outputs[0],shaderMix.inputs[2])" >> .\import.txt
            "links.new(shaderSpecImg.outputs[0],shaderSpec.inputs[0])" >> .\import.txt
            }   
                    
        if ($_.Map -eq "Bumpmap") {
            $matnormal =  $_.file.replace(".tif","$imageformat").replace(".dds","$imageformat").replace("/","\\") 
            "matNormal=bpy.data.images.load(filepath=`"$basedir\\$matnormal`")" >> .\import.txt
            "shaderNormalImg=TreeNodes.nodes.new('ShaderNodeTexImage')" >> .\import.txt
            "shaderRGBtoBW=TreeNodes.nodes.new('ShaderNodeRGBToBW')" >> .\import.txt
            "shaderNormalImg.image=matNormal" >> .\import.txt
            "shaderNormalImg.location = -100,100" >> .\import.txt
            "shaderRGBtoBW.location = 100,100" >> .\import.txt
            "links.new(shaderNormalImg.outputs[0],shaderRGBtoBW.inputs[0])" >> .\import.txt
            "links.new(shaderRGBtoBW.outputs[0],shout.inputs[2])" >> .\import.txt
        }
    }
}

#  *** PARSING OBJs ***
#  Start parsing out $mechline
$cdffile.CharacterDefinition.attachmentlist.Attachment | % {
    #TODO:  If you're reading a .cdf file here, it's recursive and you'll have to load in a few more files.  For now, just replace to .obj
    #       for basic cockpit.
    
	$aname = $_.AName
    $rotation = $_.Rotation
    $position = $_.Position
    $bonename = $_.BoneName.replace(" ","_")
    $binding = $_.Binding
    $binding = $binding.replace(".cdf",".obj")
    $binding = $binding.replace(".cga",".obj")
    $binding = $binding.replace(".cgf",".obj")
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
    #write-host "Matname for $objectname is $matname"

    # Time to generate the commands (in $parsedline, an array)
	$parsedline = @()
    # if it's a cockpit item, it'll have multiple groups.  to avoid screwing up naming, we will import these keeping the vertex
    # order with split_mode('OFF').  We do NOT want to remove doubles though, as this destroys the UVMap.
    if ( $objectname.Contains("cockpit")) {
        $parsedline += $scriptimport + "(filepath=`"$basedir\\$binding_modified`",use_groups_as_vgroups=True,split_mode=`'OFF`')" }
    else {
	    $parsedline += $scriptimport + "(filepath=`"$basedir\\$binding_modified`",use_groups_as_vgroups=True,split_mode=`'OFF`')" }
    
    # set new object as the active object
    $parsedline += $scriptscene + "=bpy.data.objects[`"$objectname`"]"
    # Parent the object to the Armature:  Assumes armature name is Armature and that it's been imported!
    # $parsedline += $scriptscene + "=bpy.data.objects[`"Armature`"]"
    # We may at this point (someday) to replace $objectname (above) with the $Aname, but for now let's stick with $objectname
	$parsedline += $scriptrotationmode 
	$parsedline += $scriptrotation + "=[$rotation]"
	$parsedline += $scripttransform + "(value=($position))"
	$parsedline += $scriptclearmaterial
	$parsedline += $scriptseteditmode
	# Check to see if it's a cockpit item, and if so don't remove doubles!
    if ( !$objectname.Contains("cockpit")) {
        $parsedline += $scriptremovedoubles }

	$parsedline += $scripttristoquads
    # Create a vertex group with the bone name.  This makes parenting to armature super easy!
    $parsedline += "bpy.ops.object.vertex_group_add()"
    $parsedline += "bpy.context.object.vertex_groups.active.name = `"$bonename`""
    $parsedline += "bpy.ops.mesh.select_all(action=`'SELECT`')"
    $parsedline += "bpy.ops.object.vertex_group_assign()"
    $parsedline += "bpy.ops.mesh.select_all(action=`'TOGGLE`')"

	$parsedline += $scriptsetobjectmode
    $parsedline += "bpy.context.object.data.materials.append($matname)"

	foreach ( $line in $parsedline ) {
		#write-host $line
		$line >> .\import.txt
	}
}
"" >> .\import.txt # Send a final line feed.


