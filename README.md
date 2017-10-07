## Mech Importer

This is the next release of Mech Importer:  a powershell script used to help import Cryengine mechs from MWO into Blender.

When you run this program, it will generate a file called **`import.txt`**.  This file contains the Blender python commands necessary to import the objects and build the mech.  You copy all the text in this import.txt file into the clipboard and then paste it into the Blender python console.  Yes, this isn't ideal, and there are plans to change this to just be an add-on in Blender.  However, it works, which is an important part of getting things done. ;)  See the Tutorial Video section for the full process in action.

There are some significant changes to this version.
* It is geared towards working with the new [cgf-converter tool](https://github.com/markemp/cryengine-converter).  If you are using old versions of this tool or cgf-converter, you will probably have issues.
* This only works with [Blender 2.79](http://blender.org) or newer (uses the Principled BSDF shader).

### Usage
```
Usage:  mech-importer <-cdffile <mech .cdf file location>><[-objectdir '<directory to \Object>']> <[-dae|-obj]> <-imageformat [dds]|[tif]>
        Takes a mech's cdf file (in Objects\Mechs\<mech>) and creates an import.txt file that
        can be pasted into the Blender python console.  This will import all the mech parts
        (assuming they've been converted to .dae or .obj) into Blender and create the appropriate
        materials.

        If .cdf file isn't specified, Mech Importer checks the current directory.
        The following variables need to be properly defined:
             `$objectdir:  Where you extracted the object.pak files (and skins)
             `$imageformat:  What image format you are using (default .dds.  Also supports tif)

         This will only fully work when imported into Blender 2.79 or newer, as it uses the PrincipledBSDF shader.
```

### Best Practices
For best results, be sure to:
* Create a scripts directory where you store this and cgf-converter, and add that directory to the path.
   * [Windows 10](https://superuser.com/questions/949560/how-do-i-set-system-environment-variables-in-windows-10)
   * [Windows 7 (but you should really be on Windows 10)](https://stackoverflow.com/questions/23400030/windows-7-add-path)
* Use Powershell and navigate around your file system from the command prompt.
* Extract **all** the .pak files in the game to a dedicated directory structure, and preserve that structure.  Cryengine/Lumberyard makes a ton of assumptions on where certain files are, and if it can't find files it needs, things don't work.
* Run the command from the directory where the mech .cdf file is (Objects/Mechs/<mech>).
* **Always** use the -objectdir argument and point it to where the Objects directory is found.
* Don't use -obj any more.  Waveform is a very limited format and you should move to Collada (dae).

### Tutorial video
* Coming soon!

### Example
![Mech Importer Example](https://heffaypresentsstorage.blob.core.windows.net/images/mech-importer_sample.PNG)

### Known issues
* The mechs only are provided with the default textures.  If you want to use camo patterns, you need to use the [MWO_CAMOv3.blend](https://heffaypresentsstorage.blob.core.windows.net/misc/mwo_camo_v3.blend) material, created by Andreas80.  You can append the material from this blend file into your project and replace the existing materials (<mech>_body, <mech>_variant) using the various camo patterns with custom colors.
* The hardpoints (shown as empties in Blender) are parented to the geometry they belong to, but follow the root bone instead of their parent object.

### Help!
* If you are having issues, please use the Issues tab at Github to report them.  That will help us track and resolve them in a timely manner.

Thank you!
