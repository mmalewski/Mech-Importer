# Mech Importer

## Mech Importer has been converted to a Blender Add-on!

### Features:
* Imports a fully rigged mech with standard materials into Blender with the Cycles render engine.
* Basic node layout for the 3 main materials (<mech>_body, <mech>_variant, decal), along with the <mech>_generic material where listed.
* Complete UV layouts for all the various components.
* Fully rigged with IK bones, for advanced animation techniques.
* Included MWO_Camo_v3 blend file (created by Andreas80), which allows the replacement of the standard materials with camo patterns and customized colors (see tutorial for instructions on implementation).

*Note:*  

### Notes:
* Requires Blender 2.79 or newer, as it uses the PrincipledBSDF shader node
* This add-on requires that all the .cga and/or .cgf files in the mech's body directory be converted with the [Cryengine Converter](https://github.com/markemp/Cryengine-Converter) utility to Collada (.dae) format.  It also assumes that the texture images will be in the original DDS format, although future improvements may also work with TIF.

### Installation:

1. Download the zip file from [Heffay Presents](https://www.heffaypresents.com/GitHub) or from [GitHub](https://github.com/Markemp/Mech-Importer/Releases).
2. Extract the files to a working directory.
3. In Blender, go to File -> User Preferences -> Add-ons and click on "Install Add-on from File..."
4. Navigate to the mech-importer.py file that was extracted in step 2 and click the "Install Add-on from File..." button.  This will copy it to your Blender user directory.
5. Back in the User Preferences window, under the Import-Export area, find "Import-Export: Mech Importer" and enable it.
6. Click on Save User Settings so that it is available every time you start Blender.

### Usage:

1. Using [Cryengine Converter](https://github.com/markemp/Cryengine-Converter), convert all the .cga and .cgf files in the mech directory (/Objects/Mechs/<mechname>).
2. In Blender, go to File -> Import -> Mech and navigate to the cdf file for the mech you want to import (/Objects/Mechs/<mech>).
3. Select the .cdf file and click the "Import Mech" button.  The script will process for a few seconds, and you should see a fully rigged mech!

### Best Practices
For best results, be sure to:
* Extract **all** the .pak files in the game to a dedicated directory structure, and preserve that structure.  Cryengine/Lumberyard makes a ton of assumptions on where certain files are, and if it can't find files it needs, things don't work.
* Don't use -obj any more.  Waveform is a very limited format and you should move to Collada (dae).

### Tutorial video
* Coming soon!

### Known issues
* The mechs only are provided with the default textures.  If you want to use camo patterns, you need to use the [MWO_CAMOv3.blend](https://heffaypresentsstorage.blob.core.windows.net/misc/mwo_camo_v3.blend) material, which is included in the .zip file.  You can append the material from this blend file into your project and replace the existing materials (<mech>_body, <mech>_variant) using the various camo patterns with custom colors.

### Help!
* If you are having issues, please use the Issues tab at Github to report them.  That will help us track and resolve them in a timely manner.

### Thanks:
* Andreas80, for the MWO_Camo_v3.blend file

Thank you!
