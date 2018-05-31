import bpy
import textureUtil
import install
import pbrt
import sceneParser
import generalUtil

import os
import math
import subprocess

# =============================================================================
# Utils

def wline(f, t):
    f.write("{}\n".format(t))

def runCmd(cmd, stdout=None, cwd=None, env=None):
    stdoutInfo = ""
    if stdout is not None:
        stdoutInfo = " > {}".format(stdout.name)
    print(">>> {}{}".format(cmd, stdoutInfo))
    subprocess.call(cmd, shell=False, stdout=stdout, cwd=cwd, env=env)

def appendFile(sourcePath, destFile):
    sourceFile = open(sourcePath, 'r')
    for line in sourceFile:
        destFile.write(line)
    sourceFile.close()

# =============================================================================
# Materials generation

def createEmptyMaterialObject():
    m = generalUtil.emptyObject()
    m.iileMaterial = "MATTE"
    m.iileMatteColorTexture = ""
    m.iileMatteColor = [1.0, 0.0, 1.0] # Bright purple
    return m

def processMatteMaterial(matName, outDir, block, matObj):
    block.appendLine(2, '"string type" "matte"')
    if matObj.iileMatteColorTexture == "":
        # Diffuse color
        block.appendLine(2, '"rgb Kd" [ {} {} {} ]' \
            .format(matObj.iileMatteColor[0],
                matObj.iileMatteColor[1],
                matObj.iileMatteColor[2]))
    else:
        # Diffuse texture
        # Get the absolute path of the texture
        print("Texture detected for material {}".format(matName))
        texSource = matObj.iileMatteColorTexture
        destName = textureUtil.addTexture(texSource, outDir, block)
        # Set Kd to the texture
        materialLine = '"texture Kd" "{}"'.format(destName)
        block.appendLine(2, materialLine)

def processPlasticMaterial(matName, outDir, block, matObj):
    block.appendLine(2, '"string type" "plastic"')

    # Diffuse
    if matObj.iilePlasticDiffuseTexture == "":
        # Diffuse color
        block.appendLine(2, '"rgb Kd" [ {} {} {} ]' \
            .format(matObj.iilePlasticDiffuseColor[0],
                matObj.iilePlasticDiffuseColor[1],
                matObj.iilePlasticDiffuseColor[2]))
    else:
        # Diffuse texture
        texSource = matObj.iilePlasticDiffuseTexture
        destName = textureUtil.addTexture(texSource, outDir, block)
        # Set Kd
        materialLine = '"texture Kd" "{}"'.format(destName)
        block.appendLine(2, materialLine)

    # Specular
    if matObj.iilePlasticSpecularTexture == "":
        # Specular color
        block.appendLine(2, '"rgb Ks" [ {} {} {} ]'\
            .format(matObj.iilePlasticSpecularColor[0],
                matObj.iilePlasticSpecularColor[1],
                matObj.iilePlasticSpecularColor[2])
        )
    else:
        # Specular texture
        texSource = matObj.iilePlasticSpecularTexture
        destName = textureUtil.addTexture(texSource, outDir, block)
        # Set Kd
        materialLine = '"texture Ks" "{}"'.format(destName)
        block.appendLine(2, materialLine)

    # Roughness
    if matObj.iilePlasticRoughnessTexture == "":
        roughnessLine = '"float roughness" [{}]'.format(matObj.iilePlasticRoughnessValue)
        block.appendLine(2, roughnessLine)
    else:
        texSource = matObj.iilePlasticRoughnessTexture
        destName = textureUtil.addTexture(texSource, outDir, block, "float")
        roughnessLine = '"texture roughness" "{}"'.format(destName)
        block.appendLine(2, roughnessLine)

    # remaproughness
    remapLine = '"bool remaproughness" "true"'
    block.appendLine(2, remapLine)

# Render engine ================================================================================

class IILERenderEngine(bpy.types.RenderEngine):
    bl_idname = "iile_renderer" # internal name
    bl_label = "IILE Renderer" # Visible name
    bl_use_preview = False # capabilities

    def render(self, scene):

        # Check first-run installation
        install.install()

        # Compute film dimensions
        scale = scene.render.resolution_percentage / 100.0
        sx = int(scene.render.resolution_x * scale)
        sy = int(scene.render.resolution_y * scale)

        print("Starting render, resolution {} {}".format(sx, sy))

        # Compute pbrt executable path
        pbrtExecPath = install.getExecutablePath(
            scene.iilePath,
            pbrt.DEFAULT_IILE_PROJECT_PATH,
            "pbrt"
        )
        obj2pbrtExecPath = install.getExecutablePath(
            scene.iilePath,
            pbrt.DEFAULT_IILE_PROJECT_PATH,
            "obj2pbrt"
        )

        if pbrtExecPath is None:
            raise Exception("PBRT executable not found")
        if obj2pbrtExecPath is None:
            raise Exception("OBJ2PBRT executable not found")

        print("PBRT: {}".format(pbrtExecPath))
        print("OBJ2PBRT: {}".format(obj2pbrtExecPath))

        # Determine PBRT project directory
        if not os.path.exists(scene.iilePath):
            # Check fallback
            if not os.path.exists(pbrt.DEFAULT_IILE_PROJECT_PATH):
                print("WARNING no project directory found. Are you using vanilla PBRTv3? Some features might not work, such as IILE integrator and GUI renderer")
            else:
                scene.iilePath = pbrt.DEFAULT_IILE_PROJECT_PATH

        rootDir = os.path.abspath(os.path.join(scene.iilePath, ".."))

        # Get the output path
        outDir = bpy.data.scenes["Scene"].render.filepath
        outDir = bpy.path.abspath(outDir)
        print("Out dir is {}".format(outDir))
        outObjPath = os.path.join(outDir, "exp.obj")
        outExpPbrtPath = os.path.join(outDir, "exp.pbrt")
        outExp2PbrtPath = os.path.join(outDir, "exp2.pbrt")
        outScenePath = os.path.join(outDir, "scene.pbrt")

        # Create exporting script
        expScriptPath = os.path.join(outDir, "exp.py")
        expScriptFile = open(expScriptPath, "w")
        wline(expScriptFile, 'import bpy')
        wline(expScriptFile, 'outobj = "{}"'.format(outObjPath))
        wline(expScriptFile, 'bpy.ops.export_scene.obj(filepath=outobj, axis_forward="Y", axis_up="-Z", use_materials=True)')
        expScriptFile.close()

        blenderPath = bpy.app.binary_path
        projectPath = bpy.data.filepath

        cmd = [
            blenderPath,
            projectPath,
            "--background",
            "--python",
            expScriptPath
        ]
        runCmd(cmd)

        print("OBJ export completed")

        # Run obj2pbrt
        cmd = [
            obj2pbrtExecPath,
            outObjPath,
            outExpPbrtPath
        ]
        runCmd(cmd, cwd=outDir)

        # Run pbrt --toply
        cmd = [
            pbrtExecPath,
            "--toply",
            outExpPbrtPath
        ]
        outExp2PbrtFile = open(outExp2PbrtPath, "w")
        runCmd(cmd, stdout=outExp2PbrtFile, cwd=outDir)
        outExp2PbrtFile.close()

        # Create headers and footers -------------------------------------------------
        outSceneFile = open(outScenePath, "w")

        # Create headers

        wline(outSceneFile, 'Film "image" "integer xresolution" {} "integer yresolution" {}'.format(sx, sy))

        integratorName = "path"
        if bpy.context.scene.iileIntegrator == "PATH":
            integratorName = "path"
        elif bpy.context.scene.iileIntegrator == "IILE":
            integratorName = "iispt"
        else:
            raise Exception("Unrecognized iileIntegrator {}".format(
                bpy.context.scene.iileIntegrator))
        wline(outSceneFile, 'Integrator "{}"'.format(integratorName))

        samplerName = "random"
        if bpy.context.scene.iileIntegratorPathSampler == "RANDOM":
            samplerName = "random"
        elif bpy.context.scene.iileIntegratorPathSampler == "SOBOL":
            samplerName = "sobol"
        elif bpy.context.scene.iileIntegratorPathSampler == "HALTON":
            samplerName = "halton"
        else:
            raise Exception("Unrecognized sampler {}".format(bpy.context.scene.iileIntegratorPathSampler))

        wline(outSceneFile, 'Sampler "{}" "integer pixelsamples" {}'.format(samplerName, bpy.context.scene.iileIntegratorPathSamples))

        wline(outSceneFile, 'Scale -1 1 1')

        # Get camera
        theCameraName = bpy.context.scene.camera.name
        theCamera = bpy.data.cameras[theCameraName]

        bpy.context.scene.camera.rotation_mode = "AXIS_ANGLE"
        print("Camera rotation axis angle is {} {} {} {}".format(bpy.context.scene.camera.rotation_axis_angle[0], bpy.context.scene.camera.rotation_axis_angle[1], bpy.context.scene.camera.rotation_axis_angle[2], bpy.context.scene.camera.rotation_axis_angle[3]))

        # Write camera rotation
        cameraRotationAmount = bpy.context.scene.camera.rotation_axis_angle[0]
        cameraRotationAmount = math.degrees(cameraRotationAmount)
        cameraRotationX, cameraRotationY, cameraRotationZ = \
            bpy.context.scene.camera.rotation_axis_angle[1:]
        # Flip Y
        cameraRotationY = -cameraRotationY
        wline(outSceneFile, 'Rotate {} {} {} {}'.format(
            cameraRotationAmount, cameraRotationX,
            cameraRotationY, cameraRotationZ))

        # Write camera translation
        cameraLocX, cameraLocY, cameraLocZ = bpy.context.scene.camera.location
        # Flip Y
        cameraLocY = -cameraLocY
        wline(outSceneFile, 'Translate {} {} {}'.format(
            cameraLocX, cameraLocY, cameraLocZ))

        # Write camera fov
        wline(outSceneFile, 'Camera "perspective" "float fov" [{}]'.format(math.degrees(theCamera.angle / 2.0)))

        # Write world begin
        wline(outSceneFile, 'WorldBegin')

        # Copy content from outExp2Pbrt
        appendFile(outExp2PbrtPath, outSceneFile)

        # Write world end
        wline(outSceneFile, 'WorldEnd')

        outSceneFile.close()

        # -----------------------------------------------------------
        # Scene transformation
        doc = sceneParser.SceneDocument()
        doc.parse(outScenePath)
        blocks = doc.getBlocks()

        for block in blocks:

            # Set area light emission color
            if block.isAreaLightSource():
                print("Processing an area light source")
                matName = block.getAssignedMaterial()
                print(matName)
                matObj = bpy.data.materials[matName]
                emitIntensity = matObj.emit
                emitColor = [0.0, 0.0, 0.0]
                emitColor[0] = emitIntensity * matObj.iileEmission[0]
                emitColor[1] = emitIntensity * matObj.iileEmission[1]
                emitColor[2] = emitIntensity * matObj.iileEmission[2]
                block.replaceLine(3, '"rgb L"',
                    '"rgb L" [ {} {} {} ]'.format(
                        emitColor[0], emitColor[1], emitColor[2]))

            # Set material properties
            if block.isMakeNamedMaterial():
                matName = block.getMaterialDefinitionName()
                print("Processing material {}".format(matName))
                if matName not in bpy.data.materials:
                    matObj = createEmptyMaterialObject()
                else:
                    matObj = bpy.data.materials[matName]
                block.clearBody()
                # Write material type
                # MATTE
                if matObj.iileMaterial == "MATTE":
                    processMatteMaterial(matName, outDir, block, matObj)
                # PLASTIC
                elif matObj.iileMaterial == "PLASTIC":
                    processPlasticMaterial(matName, outDir, block, matObj)

                else:
                    raise Exception("Unrecognized material {}".format(
                        matObj.iileMaterial))


        doc.write(outScenePath)

        print("Rendering finished.")

        if (bpy.context.scene.iileIntegrator == "IILE") and bpy.context.scene.iileStartRenderer:
            print("Starting IILE GUI...")

            # Setup PATH for nodejs executable
            nodeBinDir = install.findNodeDir(scene.iilePath)
            newEnv = os.environ.copy()
            if nodeBinDir is not None:
                oldPath = newEnv["PATH"]
                addition = ':{}'.format(nodeBinDir)
                if not oldPath.endswith(addition):
                    oldPath = oldPath + addition
                newEnv["PATH"] = oldPath
                print("Updated PATH to {}".format(oldPath))

            guiDir = os.path.join(rootDir, "gui")
            electronPath = os.path.join(guiDir,
                "node_modules",
                "electron",
                "dist",
                "electron")
            jsPbrtPath = os.path.join(rootDir,
                "bin",
                "pbrt")
            cmd = []
            cmd.append(electronPath)
            cmd.append("main.js")
            cmd.append(jsPbrtPath)
            cmd.append(outScenePath)
            cmd.append("{}".format(bpy.context.scene.iileIntegratorIileIndirect))
            cmd.append("{}".format(bpy.context.scene.iileIntegratorIileDirect))
            runCmd(cmd, cwd=guiDir, env=newEnv)

        result = self.begin_result(0, 0, sx, sy)
        self.end_result(result)